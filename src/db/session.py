"""数据库连接 / session 管理（SQLAlchemy 2.0 async 模式）。

为什么用 async：
- 整个项目用 asyncio（Telegram bot、Playwright、OpenAI 都是 async）
- 同步 DB 调用会阻塞事件循环 → 整个 bot 卡住
- async session 用 asyncpg 驱动，跟 event loop 协作

为什么有 expire_on_commit=False：
- 默认 commit 后所有对象的属性会失效，下次访问要重新查 DB
- 我们大多数场景在 service 层用完对象就丢，不需要这种 lazy reload
- 关掉省一次 query，也避免"对象已 expire"错误
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # True 时打印所有 SQL，debug 用
    pool_pre_ping=True,  # 每次取连接前 ping 一下，防止 DB 重启后拿到死连接
)

# 全局 session 工厂，service 层用：
#   async with async_session() as session: ...
async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
