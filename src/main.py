"""Telegram bot 入口。

Run (from project root):
    uv run python -m src.main

注意必须用 `python -m src.main`，不能用 `python src/main.py` ——
后者会把 src/ 加进 sys.path 而不是项目根，导致 `from src.bot.app import ...` 找不到。
"""

import logging

from src.bot.app import build_application
from src.utils.logger import setup_logging

# 注意：不需要 load_dotenv()，pydantic-settings 在 src.config 里
# 已经声明了 env_file=".env"，导入 settings 时自动加载。

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()

    app = build_application()
    logger.info("Bot starting in polling mode...")
    app.run_polling()


if __name__ == "__main__":
    main()
