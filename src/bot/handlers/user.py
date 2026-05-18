"""用户面 Telegram handler。

- /start：欢迎语
- /subscribe：申请订阅，通知管理员审批
- /unsubscribe：取消订阅
- /status：查询自己订阅状态
- /digest：手动拉一份当日 digest 到自己对话（管理员 + 订阅者可用）
- 未知命令兜底
"""

import logging

from telegram import Update, User
from telegram.ext import ContextTypes

from src.bot.handlers._digest_render import send_digest_to_chat
from src.bot.middleware import Role, require_role
from src.config import settings
from src.services import digest as digest_service
from src.services import subscription
from src.services.subscription import (
    SubscribeResult,
    SubscriptionStatus,
    TelegramUserProfile,
    UnsubscribeResult,
)

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """欢迎语，所有人可用。"""
    if update.message is None:
        return
    await update.message.reply_text(
        "你好！我是 Daily X Digest Bot。\n\n"
        "每天 21:00 (新西兰时间) 自动推送 @whyyoutouzhele 的当日推文总结。\n\n"
        "命令：\n"
        "/subscribe - 申请订阅（需管理员审批）\n"
        "/status - 查询当前状态\n"
        "/unsubscribe - 取消订阅\n"
        "/digest - 立即拉一份当日 digest（订阅者可用）"
    )


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """申请订阅。新申请写 pending_requests，并通知管理员。"""
    if update.message is None or update.effective_user is None:
        return

    if settings.ADMIN_USER_ID is None:
        logger.error("ADMIN_USER_ID is not configured; cannot accept request")
        await update.message.reply_text("系统暂时未配置管理员，无法提交申请。")
        return

    profile = _to_profile(update.effective_user)
    outcome = await subscription.request_subscription(profile)

    if outcome.result == SubscribeResult.SUBMITTED:
        await update.message.reply_text("订阅申请已提交，请等待管理员审批。")
        await _notify_admin_about_request(context, profile)
        return

    if outcome.result == SubscribeResult.ALREADY_PENDING:
        await update.message.reply_text("你的订阅申请已经在等待审批中。")
        return

    if outcome.result == SubscribeResult.ALREADY_SUBSCRIBED:
        await update.message.reply_text("你已经是订阅者。")
        return

    reason = f"\n原因：{outcome.denied_reason}" if outcome.denied_reason else ""
    await update.message.reply_text(f"你的订阅申请此前已被拒绝。{reason}")


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """取消订阅。按隐私要求从 subscribers 表硬删除。"""
    if update.message is None or update.effective_user is None:
        return

    result = await subscription.unsubscribe(update.effective_user.id)
    if result == UnsubscribeResult.UNSUBSCRIBED:
        await update.message.reply_text("已取消订阅。")
        return

    await update.message.reply_text("你当前没有订阅。")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """查询自己的订阅状态。"""
    user = update.effective_user
    if user is None or update.message is None:
        return

    status_info = await subscription.get_subscription_status(user.id)
    text = _format_status(status_info.status, status_info.denied_reason)
    if settings.ADMIN_USER_ID == user.id:
        text = f"{text}\n\n你也是管理员。"
    await update.message.reply_text(text)


@require_role(Role.ADMIN, Role.SUBSCRIBER)
async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """手动拉一份当日 digest 到自己的对话。

    开放给管理员 + 订阅者：他们都是被信任的用户，自取当日 digest 不影响他人。
    AI 成本：用 get_or_generate_digest，当天已经生成过的复用，不重复调 OpenAI。
    """
    if update.message is None or update.effective_chat is None:
        return

    chat_id = update.effective_chat.id
    screen_name = settings.TRACKED_X_AUTHOR

    await update.message.reply_text(
        f"正在为 @{screen_name} 准备当日 digest，请稍候..."
    )

    try:
        package = await digest_service.get_or_generate_digest(screen_name)
    except Exception as e:
        logger.exception("digest command failed")
        await update.message.reply_text(f"生成失败：{e}")
        return

    await send_digest_to_chat(context.bot, chat_id, package)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """未知命令兜底（PROJECT_BRIEF 6.3 节）。"""
    if update.message is None:
        return
    await update.message.reply_text(
        "Unknown command. Send /start to see available commands."
    )


def _to_profile(user: User) -> TelegramUserProfile:
    return TelegramUserProfile(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )


async def _notify_admin_about_request(
    context: ContextTypes.DEFAULT_TYPE,
    profile: TelegramUserProfile,
) -> None:
    if settings.ADMIN_USER_ID is None:
        return

    try:
        await context.bot.send_message(
            chat_id=settings.ADMIN_USER_ID,
            text=(
                "新的订阅申请：\n"
                f"user_id: {profile.user_id}\n"
                f"username: {_format_username(profile.username)}\n"
                f"first_name: {profile.first_name or '-'}\n\n"
                f"批准：/approve {profile.user_id}\n"
                f"拒绝：/deny {profile.user_id} 原因"
            ),
        )
    except Exception:
        logger.exception("failed to notify admin about subscription request")


def _format_status(status: SubscriptionStatus, reason: str | None) -> str:
    if status == SubscriptionStatus.SUBSCRIBED:
        return "当前状态：已订阅。"
    if status == SubscriptionStatus.PENDING:
        return "当前状态：待审批。"
    if status == SubscriptionStatus.DENIED:
        suffix = f"\n原因：{reason}" if reason else ""
        return f"当前状态：已拒绝。{suffix}"
    return "当前状态：未申请。"


def _format_username(username: str | None) -> str:
    if not username:
        return "-"
    return f"@{username}"
