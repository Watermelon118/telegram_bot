"""日志配置。"""

import logging
import sys

REDACTED = "[REDACTED]"


class SecretRedactionFilter(logging.Filter):
    """Redact configured secrets from all log records before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = _configured_secret_values()
        if not secrets:
            return True

        try:
            message = record.getMessage()
        except Exception:
            return True

        redacted = message
        for secret in secrets:
            redacted = redacted.replace(secret, REDACTED)

        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """初始化全局 logging。stream 显式用 sys.stdout，避免 Windows stderr 乱码。"""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=level,
        stream=sys.stdout,
    )
    root_logger = logging.getLogger()
    redaction_filter = SecretRedactionFilter()
    for handler in root_logger.handlers:
        handler.addFilter(redaction_filter)

    # httpx INFO logs include full request URLs. Telegram bot tokens are part of
    # those URLs, so keep HTTP client logs at WARNING unless debugging locally.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _configured_secret_values() -> list[str]:
    try:
        from src.config import settings
    except Exception:
        return []

    candidates = [
        settings.TELEGRAM_BOT_TOKEN,
        settings.OPENAI_API_KEY,
        settings.X_SCRAPER_COOKIES,
    ]
    return [value for value in candidates if value]
