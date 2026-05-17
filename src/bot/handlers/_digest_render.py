"""Digest 内容包 → Telegram 消息的渲染 / 发送逻辑。

放在 bot/handlers 内部（前缀 _ 表示仅 handler/push 用），原因：
- 涉及 Telegram 原生类型（InputMediaPhoto / Bot 等），属于 bot 层
- Stage 5 的 push.py（广播给所有订阅者）会复用这套渲染逻辑

设计：
- 一个公开入口 send_digest_to_chat(bot, chat_id, package)
- 内部分三段：头条媒体 + 头条文字 + 要闻列表
- 头条 caption ≤ Telegram 1024 字符上限时拼一起；超了拆成"媒体 + 文字"两条
- 媒体下载失败 / 超大视频：退化为"链接 + 说明"

按 PROJECT_BRIEF 2.1 节的格式排版。
"""

import logging

from telegram import Bot, InputMediaPhoto, InputMediaVideo

from src.services import media as media_service
from src.services.digest import DigestPackage

logger = logging.getLogger(__name__)


# Telegram 媒体 caption 上限（普通 bot）。超出会被截断或报错
TELEGRAM_CAPTION_MAX = 1024
# Telegram 文本消息上限
TELEGRAM_TEXT_MAX = 4096


async def send_digest_to_chat(
    bot: Bot, chat_id: int, package: DigestPackage
) -> None:
    """把一个 DigestPackage 完整发到指定 chat。失败不抛，调用方不用担心。"""
    # 边界 1：当日 0 条推
    if package.featured is None:
        await bot.send_message(
            chat_id,
            f"今天 @{package.author_screen_name} 没有更新。",
        )
        return

    # 第一段：头条（媒体 + 文字）
    await _send_featured(bot, chat_id, package)

    # 第二段：要闻（仅当 >= 2 条推时才出）
    if package.others:
        await _send_briefs(bot, chat_id, package)


# ===================== 头条 =====================

async def _send_featured(
    bot: Bot, chat_id: int, package: DigestPackage
) -> None:
    """发头条。媒体优先，文字作为 caption；超长 caption 自动拆开。"""
    assert package.featured is not None
    featured = package.featured
    caption = _format_featured_text(package)

    downloaded: list[media_service.DownloadedMedia] = []
    try:
        downloaded = await media_service.download_tweet_media(featured.media)
        sendable = [d for d in downloaded if not d.skipped_too_large]
        too_large = [d for d in downloaded if d.skipped_too_large]

        # 超大视频的链接说明追加到 caption 末尾
        if too_large:
            caption += "\n\n⚠️ 视频较大，请点击原推文链接查看"

        if not sendable:
            # 没有可发的媒体（无媒体 / 全下载失败 / 全超大）→ 纯文字
            await _send_text(bot, chat_id, caption)
            return

        # 媒体能发：caption 短就附 caption，长就拆
        attach_caption = len(caption) <= TELEGRAM_CAPTION_MAX
        await _send_media(
            bot, chat_id, sendable,
            caption=caption if attach_caption else None,
        )
        if not attach_caption:
            await _send_text(bot, chat_id, caption)

    finally:
        media_service.cleanup(downloaded)


def _format_featured_text(package: DigestPackage) -> str:
    """按 brief 2.1 格式拼头条正文。"""
    assert package.featured is not None
    f = package.featured
    return (
        "🔥 今日头条\n\n"
        f"{f.text}\n\n"
        f"📊 评论 {_fmt_num(f.reply_count)}"
        f" · 点赞 {_fmt_num(f.like_count)}"
        f" · 浏览 {_fmt_num(f.view_count)}\n"
        f"🔗 {f.permalink}"
    )


async def _send_media(
    bot: Bot,
    chat_id: int,
    items: list[media_service.DownloadedMedia],
    *,
    caption: str | None,
) -> None:
    """根据数量 + 类型选 send_photo / send_video / send_media_group。"""
    if len(items) == 1:
        item = items[0]
        with item.local_path.open("rb") as f:
            if item.type == "video":
                await bot.send_video(chat_id, video=f, caption=caption)
            else:
                # photo / animated_gif 都按 photo 发（gif 实际是 mp4 也能用 send_animation，
                # 暂时按 photo 简化，后续按需要扩）
                await bot.send_photo(chat_id, photo=f, caption=caption)
        return

    # 多媒体：media_group（最多 10 个；X 最多 4 张图）
    # caption 放在第一个
    group: list[InputMediaPhoto | InputMediaVideo] = []
    open_files: list = []
    try:
        for idx, item in enumerate(items):
            fh = item.local_path.open("rb")
            open_files.append(fh)
            cap = caption if idx == 0 else None
            if item.type == "video":
                group.append(InputMediaVideo(media=fh, caption=cap))
            else:
                group.append(InputMediaPhoto(media=fh, caption=cap))
        await bot.send_media_group(chat_id, media=group)
    finally:
        for fh in open_files:
            try:
                fh.close()
            except Exception:
                pass


# ===================== 要闻 =====================

async def _send_briefs(
    bot: Bot, chat_id: int, package: DigestPackage
) -> None:
    """发"今日要闻"段。超过 Telegram 4096 字时分多条。"""
    lines = [f"📰 今日要闻（共 {len(package.others)} 条）", ""]
    for t in package.others:
        s = package.summary_per_tweet.get(t.id, "[无摘要]")
        lines.append(f"• {s} 🔗 {t.permalink}")

    if package.overall_takeaway:
        lines.append("")
        lines.append("📝 整体看点：")
        lines.append(package.overall_takeaway)

    full = "\n".join(lines)
    await _send_text(bot, chat_id, full)


# ===================== 工具 =====================

async def _send_text(bot: Bot, chat_id: int, text: str) -> None:
    """长文本自动按 TELEGRAM_TEXT_MAX 分段发送。"""
    if len(text) <= TELEGRAM_TEXT_MAX:
        await bot.send_message(chat_id, text)
        return
    # 按 \n 切，尽量不切断逻辑行
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.split("\n"):
        line_size = len(line) + 1
        if size + line_size > TELEGRAM_TEXT_MAX and buf:
            chunks.append("\n".join(buf))
            buf = [line]
            size = line_size
        else:
            buf.append(line)
            size += line_size
    if buf:
        chunks.append("\n".join(buf))
    for c in chunks:
        await bot.send_message(chat_id, c)


def _fmt_num(n: int | None) -> str:
    """123456 → '123,456'。"""
    if n is None:
        return "0"
    return f"{n:,}"


__all__ = ["send_digest_to_chat", "TELEGRAM_TEXT_MAX", "TELEGRAM_CAPTION_MAX"]
