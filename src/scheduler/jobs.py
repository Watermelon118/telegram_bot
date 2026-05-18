"""APScheduler job 定义。

为什么用 AsyncIOScheduler：
- 项目整体 async（PTB / Playwright / SQLAlchemy 全 async）
- scheduler 自己也跑在 event loop 里，job 函数可以是 async
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot

from src.config import settings
from src.services import digest as digest_service
from src.services import push as push_service
from src.services.twitter import TwitterScraper

logger = logging.getLogger(__name__)


async def scrape_target_job() -> None:
    """每小时一次：抓 TRACKED_X_AUTHOR 的当前首页推文落库。

    所有异常吞掉只记日志 —— scheduler 不能因为单次失败就崩。
    """
    start = datetime.now(timezone.utc)
    screen_name = settings.TRACKED_X_AUTHOR
    logger.info("scrape_target_job start: %s", screen_name)
    try:
        async with TwitterScraper() as scraper:
            tweets = await scraper.scrape_user_timeline(screen_name)
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        logger.info(
            "scrape_target_job done: %s, %d tweets, %.1fs",
            screen_name,
            len(tweets),
            duration,
        )
    except Exception:
        # 用 logger.exception 自动带 traceback
        logger.exception("scrape_target_job failed")


async def generate_daily_digest_job() -> None:
    """每天 NZ 20:30：预生成今日 digest，避免 21:00 推送时等 AI。"""
    screen_name = settings.TRACKED_X_AUTHOR
    logger.info("generate_daily_digest_job start: %s", screen_name)
    try:
        package = await digest_service.generate_digest(screen_name)
        logger.info(
            "generate_daily_digest_job done: digest_id=%s featured=%s briefs=%d",
            package.digest_id,
            package.featured.id if package.featured is not None else None,
            len(package.others),
        )
    except Exception as e:
        logger.exception("generate_daily_digest_job failed")
        await _notify_admin(f"今日 digest 生成失败：{e}")


async def push_daily_digest_job() -> None:
    """每天 NZ 21:00：推送今日 digest 给管理员 + 所有 enabled 订阅者。"""
    logger.info("push_daily_digest_job start")
    try:
        bot = Bot(settings.TELEGRAM_BOT_TOKEN)
        result = await push_service.push_daily_digest_to_subscribers(bot)
        logger.info(
            "push_daily_digest_job done: total=%d succeeded=%d failed=%d disabled=%d",
            result.total,
            result.succeeded,
            result.failed,
            result.disabled,
        )
        if result.failed:
            await _notify_admin(
                "今日推送完成，但有失败："
                f"总数 {result.total}，成功 {result.succeeded}，"
                f"失败 {result.failed}，禁用 {result.disabled}。"
            )
    except Exception as e:
        logger.exception("push_daily_digest_job failed")
        await _notify_admin(f"今日推送任务失败：{e}")


def build_scheduler() -> AsyncIOScheduler:
    """构造调度器并注册所有 jobs。返回的 scheduler 还没 start，caller 决定何时启动。"""
    scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)
    # 每个 CronTrigger 必须显式传 timezone：APScheduler 拿到已构造的 trigger 对象时
    # 不会回灌 scheduler.timezone（base.py `_create_trigger` 对 BaseTrigger 实例直接 return）；
    # 没传则 CronTrigger 内部回退到 get_localzone()，容器内默认 UTC，
    # 导致 cron(hour=21) 实际在 UTC 21:00（NZ 09:00 次日）触发。
    tz = scheduler.timezone
    # 每小时 :05 触发，跟整点错开
    scheduler.add_job(
        scrape_target_job,
        CronTrigger(minute=5, timezone=tz),
        id="scrape_target",
        name="scrape target X author timeline hourly",
        max_instances=1,  # 上一次还没跑完不要再启新的
        coalesce=True,  # 错过的执行合并成一次
    )
    scheduler.add_job(
        generate_daily_digest_job,
        CronTrigger(hour=20, minute=30, timezone=tz),
        id="generate_daily_digest",
        name="generate daily digest before push",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        push_daily_digest_job,
        CronTrigger(hour=21, minute=0, timezone=tz),
        id="push_daily_digest",
        name="push daily digest to subscribers",
        max_instances=1,
        coalesce=True,
    )
    return scheduler


async def _notify_admin(text: str) -> None:
    if settings.ADMIN_USER_ID is None:
        return
    try:
        bot = Bot(settings.TELEGRAM_BOT_TOKEN)
        await bot.send_message(settings.ADMIN_USER_ID, text)
    except Exception:
        logger.exception("failed to notify admin from scheduler")
