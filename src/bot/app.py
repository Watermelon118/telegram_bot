"""PTB Application 构造与 handler 注册。

把 Application 的初始化跟 main 入口分开，方便：
- main.py 只管启动 / 关闭流程
- 这个 factory 单独被测试或被其他入口（webhook 模式）复用
"""

import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.bot.handlers.user import echo, start
from src.config import settings

logger = logging.getLogger(__name__)


def build_application() -> Application:
    """根据 config 造一个注册好 handler 的 PTB Application。"""
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # /start 命令
    app.add_handler(CommandHandler("start", start))
    # 任意非命令文本消息走 echo
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    logger.info("Application built with %d handler(s)", len(app.handlers[0]))
    return app
