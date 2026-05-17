"""APScheduler job 定义。

为什么用 AsyncIOScheduler：
- 项目整体 async（PTB / Playwright / SQLAlchemy 全 async）
- scheduler 自己也跑在 event loop 里，job 函数可以是 async
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import settings
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


def build_scheduler() -> AsyncIOScheduler:
    """构造调度器并注册所有 jobs。返回的 scheduler 还没 start，caller 决定何时启动。"""
    scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)
    # 每小时 :05 触发，跟整点错开
    scheduler.add_job(
        scrape_target_job,
        CronTrigger(minute=5),
        id="scrape_target",
        name="scrape target X author timeline hourly",
        max_instances=1,  # 上一次还没跑完不要再启新的
        coalesce=True,  # 错过的执行合并成一次
    )
    return scheduler
