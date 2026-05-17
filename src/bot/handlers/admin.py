"""管理员面 Telegram handler。

所有命令通过 @require_role(Role.ADMIN) 限制。
- /pending /approve /deny /revoke /subscribers：订阅审批流
- /test_digest：Stage 3 接业务，手动触发当日 digest 推给管理员自己
- /test_push /broadcast：Stage 5 推送验证和管理员公告
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers._digest_render import send_digest_to_chat
from src.bot.middleware import Role, require_role
from src.config import settings
from src.services import cost as cost_service
from src.services import digest as digest_service
from src.services import push as push_service
from src.services import subscription
from src.services.subscription import (
    ApproveResult,
    DenyResult,
    RevokeResult,
)

logger = logging.getLogger(__name__)


@require_role(Role.ADMIN)
async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    requests = await subscription.list_pending_requests()
    if not requests:
        await update.message.reply_text("当前没有待审批申请。")
        return

    lines = [f"待审批申请（共 {len(requests)} 个）："]
    for item in requests:
        lines.append(
            "\n"
            f"user_id: {item.user_id}\n"
            f"username: {_format_username(item.username)}\n"
            f"first_name: {item.first_name or '-'}\n"
            f"requested_at: {_format_datetime(item.requested_at)}\n"
            f"批准：/approve {item.user_id}\n"
            f"拒绝：/deny {item.user_id} 原因"
        )
    await update.message.reply_text("\n".join(lines))


@require_role(Role.ADMIN)
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    user_id = _parse_user_id(context)
    if user_id is None:
        await update.message.reply_text("用法：/approve <user_id>")
        return

    outcome = await subscription.approve_request(
        user_id=user_id,
        approved_by=update.effective_user.id,
    )
    if outcome.result == ApproveResult.NO_PENDING_REQUEST:
        await update.message.reply_text("没有找到这个用户的待审批申请。")
        return
    if outcome.result == ApproveResult.ALREADY_SUBSCRIBED:
        await update.message.reply_text("这个用户已经是订阅者。")
        return

    await update.message.reply_text(f"已批准 user_id={user_id} 的订阅申请。")
    await _notify_user(
        context,
        user_id,
        "你的订阅申请已通过。之后会收到每日推送。",
        update,
    )


@require_role(Role.ADMIN)
async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    user_id = _parse_user_id(context)
    if user_id is None:
        await update.message.reply_text("用法：/deny <user_id> [原因]")
        return

    reason = _parse_reason(context)
    outcome = await subscription.deny_request(user_id=user_id, reason=reason)
    if outcome.result == DenyResult.NO_PENDING_REQUEST:
        await update.message.reply_text("没有找到这个用户的待审批申请。")
        return
    if outcome.result == DenyResult.ALREADY_SUBSCRIBED:
        await update.message.reply_text("这个用户已经是订阅者。如需撤销请用 /revoke。")
        return

    await update.message.reply_text(f"已拒绝 user_id={user_id} 的订阅申请。")
    user_text = "你的订阅申请未通过。"
    if reason:
        user_text = f"{user_text}\n原因：{reason}"
    await _notify_user(context, user_id, user_text, update)


@require_role(Role.ADMIN)
async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    user_id = _parse_user_id(context)
    if user_id is None:
        await update.message.reply_text("用法：/revoke <user_id>")
        return

    outcome = await subscription.revoke_subscription(user_id)
    if outcome.result == RevokeResult.NOT_SUBSCRIBED:
        await update.message.reply_text("这个用户当前不是有效订阅者。")
        return

    await update.message.reply_text(f"已撤销 user_id={user_id} 的订阅。")
    await _notify_user(
        context,
        user_id,
        "你的订阅已被管理员撤销。",
        update,
    )


@require_role(Role.ADMIN)
async def subscribers_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None:
        return

    subscribers = await subscription.list_subscribers()
    if not subscribers:
        await update.message.reply_text("当前没有订阅者。")
        return

    lines = [f"当前订阅者（共 {len(subscribers)} 个）："]
    for item in subscribers:
        lines.append(
            "\n"
            f"user_id: {item.user_id}\n"
            f"username: {_format_username(item.username)}\n"
            f"first_name: {item.first_name or '-'}\n"
            f"approved_at: {_format_datetime(item.approved_at)}"
        )
    await update.message.reply_text("\n".join(lines))


@require_role(Role.ADMIN)
async def test_digest(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """手动触发当日 digest，仅推给管理员自己（PROJECT_BRIEF 2.2 节）。

    用途：开发期 / 部署后验证全流程是否正常，不影响真订阅者。
    """
    if update.message is None or update.effective_chat is None:
        return

    chat_id = update.effective_chat.id
    screen_name = settings.TRACKED_X_AUTHOR

    await update.message.reply_text(
        f"正在为 @{screen_name} 生成当日 digest，请稍候..."
    )

    try:
        package = await digest_service.generate_digest(screen_name)
    except Exception as e:
        logger.exception("generate_digest failed")
        await update.message.reply_text(f"生成失败：{e}")
        return

    await send_digest_to_chat(context.bot, chat_id, package)


@require_role(Role.ADMIN)
async def test_push(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """手动触发一次今日推送，只发给管理员。"""
    if update.message is None:
        return

    await update.message.reply_text("正在执行 test push，请稍候...")
    try:
        result = await push_service.send_test_digest_to_admin(context.bot)
    except Exception as e:
        logger.exception("test_push failed")
        await update.message.reply_text(f"test push 失败：{e}")
        return

    await update.message.reply_text(
        "test push 完成："
        f"成功 {result.succeeded}，失败 {result.failed}。"
    )


@require_role(Role.ADMIN)
async def broadcast(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """向所有订阅者广播一条管理员公告。"""
    if update.message is None:
        return

    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text("用法：/broadcast <消息>")
        return

    await update.message.reply_text("正在广播，请稍候...")
    result = await push_service.broadcast_message(context.bot, text)
    await update.message.reply_text(
        "广播完成："
        f"总数 {result.total}，成功 {result.succeeded}，"
        f"失败 {result.failed}，禁用 {result.disabled}。"
    )


@require_role(Role.ADMIN)
async def cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """查看近 N 天 OpenAI 调用成本。"""
    if update.message is None:
        return

    days = _parse_days(context)
    if days is None:
        await update.message.reply_text("用法：/cost [days]，例如 /cost 7")
        return

    summary = await cost_service.summarize_ai_cost(days)
    await update.message.reply_text(
        f"近 {summary.days} 天 AI 成本：\n"
        f"调用次数：{summary.call_count}\n"
        f"输入 tokens：{summary.input_tokens:,}\n"
        f"输出 tokens：{summary.output_tokens:,}\n"
        f"成本：${summary.cost_usd:.6f} USD"
    )


def _parse_user_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    if not context.args:
        return None
    try:
        return int(context.args[0])
    except ValueError:
        return None


def _parse_reason(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    if not context.args or len(context.args) < 2:
        return None
    reason = " ".join(context.args[1:]).strip()
    return reason or None


def _parse_days(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    if not context.args:
        return 7
    try:
        days = int(context.args[0])
    except ValueError:
        return None
    if days <= 0 or days > 365:
        return None
    return days


async def _notify_user(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    text: str,
    update: Update,
) -> None:
    try:
        await context.bot.send_message(chat_id=user_id, text=text)
    except Exception:
        logger.exception("failed to notify user_id=%d", user_id)
        if update.message is not None:
            await update.message.reply_text(
                "状态已更新，但通知用户失败。完整错误已写入日志。"
            )


def _format_username(username: str | None) -> str:
    if not username:
        return "-"
    return f"@{username}"


def _format_datetime(value: datetime) -> str:
    tz = ZoneInfo(settings.TIMEZONE)
    return value.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
