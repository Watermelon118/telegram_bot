"""面向普通用户的 Telegram handler。

当前只有 /start 和 echo 占位实现，Stage 4 会加 /subscribe /unsubscribe /status。
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /start 命令：欢迎语。"""
    await update.message.reply_text(
        "Hi! Send me anything, I'll echo it back. (More commands coming.)"
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """临时占位：把任意文本原样回复，方便联调。Stage 4 会替换成正经命令路由。"""
    user_text = update.message.text
    logger.info("Received: %s", user_text)
    await update.message.reply_text(user_text)
