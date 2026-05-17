"""推文媒体下载 service。

职责：从 Tweet.media JSONB 里的 URL 下载图片/视频到本地临时文件，
返回本地路径供 Telegram 发送。

设计：
- 用 tempfile.mkdtemp() 给每次推送开一个唯一子目录，方便整批清理
- httpx.AsyncClient 复用连接（同一推文可能 4 张图）
- 视频走 video_url（高码率版），图片走 url（media_url_https）
- 视频如果超过 TELEGRAM_VIDEO_LIMIT_BYTES（50MB bot 限制）→ 返回 None，
  上层决定退化为"缩略图 + 链接"
- 永远不要在下载阶段抛异常拖垮 digest：单个媒体失败回 None，记 warning
"""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Telegram bot 上传上限（普通 bot）；超过的视频不传，发链接
TELEGRAM_VIDEO_LIMIT_BYTES = 50 * 1024 * 1024

# 单文件下载超时
_DOWNLOAD_TIMEOUT_SECONDS = 60.0


@dataclass
class DownloadedMedia:
    """一个已下载的媒体文件。"""

    type: str  # 'photo' | 'video' | 'animated_gif'
    local_path: Path
    size_bytes: int
    # 是否因超 Telegram 限制而被跳过（path 不存在）。上层用来决定是否退化
    skipped_too_large: bool = False
    # 原始 URL，超大时回退到"发链接"用
    source_url: str | None = None


async def download_tweet_media(
    media_items: list[dict[str, Any]] | None,
) -> list[DownloadedMedia]:
    """下载一条推文里所有媒体。

    输入：Tweet.media JSONB（list of {type, url, video_url?}）
    返回：DownloadedMedia 列表（顺序对应输入；下载失败的条目跳过）
    """
    if not media_items:
        return []

    tmp_dir = Path(tempfile.mkdtemp(prefix="xdigest_media_"))
    logger.info("media tmp dir: %s", tmp_dir)

    out: list[DownloadedMedia] = []
    async with httpx.AsyncClient(
        timeout=_DOWNLOAD_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as http:
        for idx, item in enumerate(media_items):
            mtype = item.get("type", "")
            # 视频走 video_url（高码率 mp4），图片走 url
            url = item.get("video_url") if mtype == "video" else item.get("url")
            if not url:
                logger.warning("media[%d] missing url, skipped: %s", idx, item)
                continue

            try:
                downloaded = await _download_one(http, url, mtype, tmp_dir, idx)
                if downloaded is not None:
                    out.append(downloaded)
            except Exception as e:
                # 单个媒体失败不能拖垮整批
                logger.warning(
                    "media[%d] download failed url=%s: %s", idx, url, e
                )
                continue

    logger.info(
        "downloaded %d/%d media files to %s", len(out), len(media_items), tmp_dir
    )
    return out


async def _download_one(
    http: httpx.AsyncClient,
    url: str,
    mtype: str,
    tmp_dir: Path,
    idx: int,
) -> DownloadedMedia | None:
    """下载一个媒体文件。返回 None 表示要跳过（超大视频）。"""
    # 视频先 HEAD 看大小，超限直接退化
    if mtype == "video":
        try:
            head = await http.head(url)
            content_length = int(head.headers.get("content-length", "0") or "0")
            if content_length > TELEGRAM_VIDEO_LIMIT_BYTES:
                logger.info(
                    "video too large (%.1f MB > 50 MB), will send link only",
                    content_length / 1024 / 1024,
                )
                return DownloadedMedia(
                    type=mtype,
                    local_path=Path(),  # 占位，不会被用到
                    size_bytes=content_length,
                    skipped_too_large=True,
                    source_url=url,
                )
        except Exception as e:
            # HEAD 失败不算致命，尝试 GET 也行（最差下完才发现超大）
            logger.warning("HEAD failed for %s, falling back to GET: %s", url, e)

    # 推断扩展名（URL path 结尾，Telegram 不强求但便于 debug）
    suffix = _guess_suffix(url, mtype)
    local_path = tmp_dir / f"{idx}{suffix}"

    async with http.stream("GET", url) as resp:
        resp.raise_for_status()
        size = 0
        with local_path.open("wb") as f:
            async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                f.write(chunk)
                size += len(chunk)
                if mtype == "video" and size > TELEGRAM_VIDEO_LIMIT_BYTES:
                    # 流式下载途中也守一道
                    logger.info("video exceeded limit mid-download, abort")
                    f.close()
                    local_path.unlink(missing_ok=True)
                    return DownloadedMedia(
                        type=mtype,
                        local_path=Path(),
                        size_bytes=size,
                        skipped_too_large=True,
                        source_url=url,
                    )

    return DownloadedMedia(
        type=mtype,
        local_path=local_path,
        size_bytes=size,
        source_url=url,
    )


def _guess_suffix(url: str, mtype: str) -> str:
    """从 URL 末尾或类型猜文件扩展名。Telegram 不依赖扩展名，纯为调试方便。"""
    # 取 URL path 部分最后一个 . 后的内容（去 query string）
    path = url.split("?", 1)[0]
    if "." in path.rsplit("/", 1)[-1]:
        ext = path.rsplit(".", 1)[-1]
        if 0 < len(ext) <= 5:
            return f".{ext}"
    # 兜底
    if mtype == "video":
        return ".mp4"
    return ".jpg"


def cleanup(downloaded: list[DownloadedMedia]) -> None:
    """删本批所有临时文件 + 父目录。推送完后调用，避免磁盘累积。"""
    if not downloaded:
        return
    parents: set[Path] = set()
    for d in downloaded:
        if d.skipped_too_large:
            continue
        try:
            d.local_path.unlink(missing_ok=True)
            parents.add(d.local_path.parent)
        except Exception as e:
            logger.warning("failed to unlink %s: %s", d.local_path, e)
    for p in parents:
        try:
            p.rmdir()
        except OSError:
            pass  # 还有其他文件就不删
