"""管理员面 Telegram handler。

所有命令通过 @require_role(Role.ADMIN) 限制。
具体业务逻辑 Stage 4 才接，现在占位。
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.middleware import Role, require_role

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
