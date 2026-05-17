"""用户面 Telegram handler。

- /start：欢迎语
- /subscribe：申请订阅（Stage 4 接管，现在占位）
- /unsubscribe：取消订阅（同上）
- /status：查询自己角色
- 未知命令兜底
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.middleware import get_user_role

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """欢迎语，所有人可用。"""
    if update.message is None:
        return
    await update.message.reply_text(
        "你好！我是 Daily X Digest Bot。\n\n"
        "每天 20:00 (新西兰时间) 自动推送 @whyyoutouzhele 的当日推文总结。\n\n"
        "命令：\n"
        "/subscribe - 申请订阅（需管理员审批）\n"
        "/status - 查询当前状态\n"
        "/unsubscribe - 取消订阅"
    )


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """申请订阅 —— Stage 4 接管。"""
    if update.message is None:
        return
    await update.message.reply_text(
        "Subscription flow not yet implemented (Stage 4)."
    )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """取消订阅 —— Stage 4 接管。"""
    if update.message is None:
        return
    await update.message.reply_text(
        "Unsubscribe not yet implemented (Stage 4)."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """查询自己角色。"""
    user = update.effective_user
    if user is None or update.message is None:
        return
    role = await get_user_role(user.id)
    await update.message.reply_text(f"你当前角色：{role.value}")


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """未知命令兜底（PROJECT_BRIEF 6.3 节）。"""
    if update.message is None:
        return
    await update.message.reply_text(
        "Unknown command. Send /start to see available commands."
    )
