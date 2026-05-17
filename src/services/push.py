"""Telegram 推送 service。

职责：
- 将 DigestPackage 广播给所有 enabled subscribers
- 记录 push_history
- 单个用户推送失败不影响其他用户
- 连续失败 3 次后禁用该订阅者

注意：这里复用 bot 层的 digest renderer，因为真正发送 Telegram 消息必须依赖
python-telegram-bot 的 Bot 类型。这是项目里明确的协议边界适配点。
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from telegram import Bot

from src.bot.handlers._digest_render import send_digest_to_chat
from src.config import settings
from src.db.models import PushHistory, Subscriber
from src.db.session import async_session
from src.services import digest as digest_service

logger = logging.getLogger(__name__)

SEND_INTERVAL_SECONDS = 0.05
DISABLE_AFTER_CONSECUTIVE_FAILURES = 3


@dataclass(frozen=True)
class PushResult:
    total: int
    succeeded: int
    failed: int
    disabled: int


async def push_daily_digest_to_subscribers(bot: Bot) -> PushResult:
    """生成/读取今日 digest，并广播给所有 enabled subscribers。"""
    package = await digest_service.get_or_generate_digest(
        settings.TRACKED_X_AUTHOR
    )
    return await send_digest_to_subscribers(bot, package)


async def send_digest_to_subscribers(
    bot: Bot,
    package: digest_service.DigestPackage,
) -> PushResult:
    """把 digest 发给所有订阅者。"""
    subscribers = await _list_enabled_subscribers()
    logger.info(
        "daily digest push start: digest_id=%s subscribers=%d",
        package.digest_id,
        len(subscribers),
    )
    result = await _send_to_many(
        subscribers,
        lambda user_id: send_digest_to_chat(bot, user_id, package),
        digest_id=package.digest_id,
        update_last_pushed=True,
    )
    logger.info(
        "daily digest push done: total=%d succeeded=%d failed=%d disabled=%d",
        result.total,
        result.succeeded,
        result.failed,
        result.disabled,
    )
    return result


async def send_test_digest_to_admin(bot: Bot) -> PushResult:
    """只给管理员推一次今日 digest，用于 /test_push。"""
    if settings.ADMIN_USER_ID is None:
        raise RuntimeError("ADMIN_USER_ID is not configured")

    package = await digest_service.get_or_generate_digest(
        settings.TRACKED_X_AUTHOR
    )
    await send_digest_to_chat(bot, settings.ADMIN_USER_ID, package)
    return PushResult(total=1, succeeded=1, failed=0, disabled=0)


async def broadcast_message(bot: Bot, text: str) -> PushResult:
    """向所有 enabled subscribers 广播一条管理员公告。"""
    subscribers = await _list_enabled_subscribers()
    logger.info("broadcast start: subscribers=%d", len(subscribers))
    result = await _send_to_many(
        subscribers,
        lambda user_id: bot.send_message(chat_id=user_id, text=text),
        digest_id=None,
        update_last_pushed=False,
    )
    logger.info(
        "broadcast done: total=%d succeeded=%d failed=%d disabled=%d",
        result.total,
        result.succeeded,
        result.failed,
        result.disabled,
    )
    return result


async def _list_enabled_subscribers() -> list[int]:
    async with async_session() as session:
        stmt = (
            select(Subscriber.user_id)
            .where(Subscriber.enabled.is_(True))
            .order_by(Subscriber.approved_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def _send_to_many(
    user_ids: list[int],
    sender,
    *,
    digest_id: int | None,
    update_last_pushed: bool,
) -> PushResult:
    succeeded = 0
    failed = 0
    disabled = 0

    for user_id in user_ids:
        try:
            await sender(user_id)
        except Exception as e:
            failed += 1
            logger.exception("push failed: user_id=%d", user_id)
            was_disabled = await _record_push_result(
                user_id=user_id,
                digest_id=digest_id,
                success=False,
                error_message=str(e),
                update_last_pushed=False,
            )
            if was_disabled:
                disabled += 1
        else:
            succeeded += 1
            await _record_push_result(
                user_id=user_id,
                digest_id=digest_id,
                success=True,
                error_message=None,
                update_last_pushed=update_last_pushed,
            )

        await asyncio.sleep(SEND_INTERVAL_SECONDS)

    return PushResult(
        total=len(user_ids),
        succeeded=succeeded,
        failed=failed,
        disabled=disabled,
    )


async def _record_push_result(
    *,
    user_id: int,
    digest_id: int | None,
    success: bool,
    error_message: str | None,
    update_last_pushed: bool,
) -> bool:
    """记录 push_history。返回 True 表示本次把用户禁用了。"""
    async with async_session() as session:
        subscriber = await session.get(Subscriber, user_id)
        if subscriber is None:
            return False

        session.add(
            PushHistory(
                digest_id=digest_id,
                user_id=user_id,
                success=success,
                error_message=error_message,
            )
        )
        if success and update_last_pushed:
            subscriber.last_pushed_at = datetime.now(timezone.utc)

        disabled = False
        if not success:
            await session.flush()
            failures = await _count_recent_consecutive_failures(session, user_id)
            if failures >= DISABLE_AFTER_CONSECUTIVE_FAILURES:
                subscriber.enabled = False
                disabled = True
                logger.warning(
                    "subscriber disabled after consecutive failures: user_id=%d failures=%d",
                    user_id,
                    failures,
                )

        await session.commit()
        return disabled


async def _count_recent_consecutive_failures(session, user_id: int) -> int:
    stmt = (
        select(PushHistory.success)
        .where(PushHistory.user_id == user_id)
        .order_by(PushHistory.sent_at.desc(), PushHistory.id.desc())
        .limit(DISABLE_AFTER_CONSECUTIVE_FAILURES)
    )
    results = list((await session.execute(stmt)).scalars().all())
    count = 0
    for success in results:
        if success:
            break
        count += 1
    return count
