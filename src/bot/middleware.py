"""权限分级中间件。

三个角色：
- admin：settings.ADMIN_USER_ID
- subscriber：在 subscribers 表中且 enabled=True
- guest：其他所有人

提供 require_role() 装饰器给 handler 用。
"""

import logging
from collections.abc import Awaitable, Callable
from enum import Enum
from functools import wraps

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from src.config import settings
from src.db.models import Subscriber
from src.db.session import async_session

logger = logging.getLogger(__name__)


class Role(str, Enum):
    ADMIN = "admin"
    SUBSCRIBER = "subscriber"
    GUEST = "guest"


async def get_user_role(user_id: int) -> Role:
    """按 user_id 查角色。admin > subscriber > guest 优先级。"""
    if (
        settings.ADMIN_USER_ID is not None
        and user_id == settings.ADMIN_USER_ID
    ):
        return Role.ADMIN

    async with async_session() as session:
        stmt = select(Subscriber).where(
            Subscriber.user_id == user_id,
            Subscriber.enabled.is_(True),
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            return Role.SUBSCRIBER

    return Role.GUEST


HandlerFunc = Callable[
    [Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]
]


def require_role(*allowed: Role) -> Callable[[HandlerFunc], HandlerFunc]:
    """装饰器：限制 handler 只允许某些角色调用。

    用法：
        @require_role(Role.ADMIN)
        async def some_handler(update, context): ...
    """
    allowed_set = set(allowed)

    def decorator(fn: HandlerFunc) -> HandlerFunc:
        @wraps(fn)
        async def wrapper(
            update: Update, context: ContextTypes.DEFAULT_TYPE
        ) -> None:
            user = update.effective_user
            if user is None:
                return
            role = await get_user_role(user.id)
            if role not in allowed_set:
                logger.warning(
                    "permission denied: user_id=%d role=%s required=%s",
                    user.id,
                    role.value,
                    [r.value for r in allowed_set],
                )
                if update.message is not None:
                    await update.message.reply_text("Not authorized.")
                return
            await fn(update, context)

        return wrapper

    return decorator
