"""管理员面 Telegram handler。

所有命令通过 @require_role(Role.ADMIN) 限制。
- /pending /approve /deny /revoke /subscribers：Stage 4 接业务
- /test_digest：Stage 3 接业务，手动触发当日 digest 推给管理员自己
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers._digest_render import send_digest_to_chat
from src.bot.middleware import Role, require_role
from src.config import settings
from src.services import digest as digest_service

logger = logging.getLogger(__name__)


@require_role(Role.ADMIN)
async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text("/pending: not yet implemented (Stage 4)")


@require_role(Role.ADMIN)
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text("/approve: not yet implemented (Stage 4)")


@require_role(Role.ADMIN)
async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text("/deny: not yet implemented (Stage 4)")


@require_role(Role.ADMIN)
async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text("/revoke: not yet implemented (Stage 4)")


@require_role(Role.ADMIN)
async def subscribers_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        "/subscribers: not yet implemented (Stage 4)"
    )


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
