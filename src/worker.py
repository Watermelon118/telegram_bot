"""Worker 进程入口：跑爬虫定时任务（未来还会加推送 job）。

跟 bot 进程分开运行：
    uv run python -m src.worker

设计原则（PROJECT_BRIEF 第 4 节）：
- bot 进程一直 polling 响应 Telegram 命令
- worker 进程一直跑定时任务
- 两进程共享数据库，不共享内存
- 一边崩了不影响另一边
"""

import asyncio
import logging

from src.scheduler.jobs import build_scheduler
from src.utils.logger import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    scheduler = build_scheduler()
    scheduler.start()
    logger.info(
        "worker started; scheduled jobs: %s",
        [j.id for j in scheduler.get_jobs()],
    )
    # 阻塞事件循环不退出。Ctrl+C 时优雅关闭。
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown()
        logger.info("worker shutdown")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
