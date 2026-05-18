"""PTB Application 构造与 handler 注册。

把 Application 的初始化跟 main 入口分开，方便：
- main.py 只管启动 / 关闭流程
- 这个 factory 单独被测试或被其他入口（webhook 模式）复用
"""

import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.bot.handlers import admin, user
from src.config import settings

logger = logging.getLogger(__name__)


def build_application() -> Application:
    """根据 config 造一个注册好 handler 的 PTB Application。"""
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # ===== 用户命令（含 admin + subscriber 共用）=====
    app.add_handler(CommandHandler("start", user.start))
    app.add_handler(CommandHandler("subscribe", user.subscribe))
    app.add_handler(CommandHandler("unsubscribe", user.unsubscribe))
    app.add_handler(CommandHandler("status", user.status))
    app.add_handler(CommandHandler("digest", user.digest))

    # ===== 管理员命令（require_role(ADMIN) 在 handler 内部检查）=====
    app.add_handler(CommandHandler("pending", admin.pending))
    app.add_handler(CommandHandler("approve", admin.approve))
    app.add_handler(CommandHandler("deny", admin.deny))
    app.add_handler(CommandHandler("revoke", admin.revoke))
    app.add_handler(CommandHandler("subscribers", admin.subscribers_list))
    app.add_handler(CommandHandler("test_push", admin.test_push))
    app.add_handler(CommandHandler("broadcast", admin.broadcast))
    app.add_handler(CommandHandler("cost", admin.cost))

    # ===== 未知命令兜底（必须放最后）=====
    app.add_handler(MessageHandler(filters.COMMAND, user.unknown))

    logger.info(
        "Application built with %d handler(s)", len(app.handlers[0])
    )
    return app
