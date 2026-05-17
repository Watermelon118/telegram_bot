"""统一配置管理。所有环境变量在这里集中声明并做类型校验。

加载顺序（优先级从高到低）：
1. 操作系统真实环境变量
2. 项目根目录 `.env` 文件
3. 这里的默认值

Usage:
    from src.config import settings
    print(settings.TELEGRAM_BOT_TOKEN)

设计原则：
- **当前 Stage 真的会用的配置 → 必填**（无默认值，缺则启动期就挂）
- **后续 Stage 才用的配置 → 可选 + 默认空**（避免开发者还没准备好 OpenAI key 时 bot 都启不动）
- 类型注解严格（int / str / bool），pydantic 自动校验
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env 里多出来的变量不报错，跳过
        case_sensitive=True,
    )

    # ============ 当前 Stage 真在用的 ============

    # Telegram bot 启动必需
    TELEGRAM_BOT_TOKEN: str

    # ============ 后续 Stage 才用，先占位 ============

    # 管理员审批所用，Stage 4 启用
    ADMIN_USER_ID: int | None = None

    # AI 摘要所用，Stage 3 启用
    OPENAI_API_KEY: str = ""

    # X 爬虫，Stage 2.7 接入
    X_SCRAPER_USERNAME: str = ""
    X_SCRAPER_COOKIES: str = ""
    X_SCRAPER_PASSWORD: str = ""
    X_SCRAPER_EMAIL: str = ""
    X_SCRAPER_EMAIL_PASSWORD: str = ""
    TRACKED_X_AUTHOR: str = "whyyoutouzhele"
    PLAYWRIGHT_BROWSER_CHANNEL: str = ""

    # 数据库，Stage 2.4-2.6 接入
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/x_digest"
    )

    # App 行为
    BOT_MODE: str = "polling"  # polling | webhook
    WEBHOOK_URL: str = ""
    WEBHOOK_PORT: int = 8443
    TIMEZONE: str = "Pacific/Auckland"
    PUSH_TIME: str = "20:00"
    LOG_LEVEL: str = "INFO"

    # OpenAI 模型选择，Stage 3 启用
    MODEL_PER_TWEET: str = "gpt-4o-mini"
    MODEL_OVERALL: str = "gpt-4o"
    MODEL_FEATURED_ANALYSIS: str = "gpt-4o"


# 单例：整个进程共享一份配置
settings = Settings()
