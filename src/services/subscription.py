"""订阅审批状态机 service。

职责边界：
- 这里负责 subscribers / pending_requests / denied_users 三张表的状态转换
- Telegram 文案、通知发送、命令参数解析放在 handler 层

状态优先级：
1. enabled subscriber -> 已订阅
2. pending request -> 待审批
3. denied user -> 已拒绝
4. 其他 -> 未申请
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import delete, select

from src.db.models import DeniedUser, PendingRequest, Subscriber
from src.db.session import async_session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramUserProfile:
    """Telegram 用户基础信息，只保存订阅审批需要的字段。"""

    user_id: int
    username: str | None
    first_name: str | None


@dataclass(frozen=True)
class PendingRequestInfo:
    user_id: int
    username: str | None
    first_name: str | None
    requested_at: datetime


@dataclass(frozen=True)
class SubscriberInfo:
    user_id: int
    username: str | None
    first_name: str | None
    approved_at: datetime


class SubscriptionStatus(StrEnum):
    NOT_APPLIED = "not_applied"
    PENDING = "pending"
    SUBSCRIBED = "subscribed"
    DENIED = "denied"


@dataclass(frozen=True)
class UserSubscriptionStatus:
    status: SubscriptionStatus
    denied_reason: str | None = None


class SubscribeResult(StrEnum):
    SUBMITTED = "submitted"
    ALREADY_PENDING = "already_pending"
    ALREADY_SUBSCRIBED = "already_subscribed"
    DENIED = "denied"


class UnsubscribeResult(StrEnum):
    UNSUBSCRIBED = "unsubscribed"
    NOT_SUBSCRIBED = "not_subscribed"


class ApproveResult(StrEnum):
    APPROVED = "approved"
    ALREADY_SUBSCRIBED = "already_subscribed"
    NO_PENDING_REQUEST = "no_pending_request"


class DenyResult(StrEnum):
    DENIED = "denied"
    ALREADY_SUBSCRIBED = "already_subscribed"
    NO_PENDING_REQUEST = "no_pending_request"


class RevokeResult(StrEnum):
    REVOKED = "revoked"
    NOT_SUBSCRIBED = "not_subscribed"


@dataclass(frozen=True)
class SubscribeOutcome:
    result: SubscribeResult
    denied_reason: str | None = None


@dataclass(frozen=True)
class ApproveOutcome:
    result: ApproveResult
    user: TelegramUserProfile | None = None


@dataclass(frozen=True)
class DenyOutcome:
    result: DenyResult
    user: TelegramUserProfile | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RevokeOutcome:
    result: RevokeResult
    user: TelegramUserProfile | None = None


async def get_subscription_status(user_id: int) -> UserSubscriptionStatus:
    """查询用户订阅状态，用于 /status。"""
    async with async_session() as session:
        subscriber = await session.get(Subscriber, user_id)
        if subscriber is not None and subscriber.enabled:
            return UserSubscriptionStatus(SubscriptionStatus.SUBSCRIBED)

        pending = await session.get(PendingRequest, user_id)
        if pending is not None:
            return UserSubscriptionStatus(SubscriptionStatus.PENDING)

        denied = await session.get(DeniedUser, user_id)
        if denied is not None:
            return UserSubscriptionStatus(
                SubscriptionStatus.DENIED,
                denied_reason=denied.reason,
            )

    return UserSubscriptionStatus(SubscriptionStatus.NOT_APPLIED)


async def request_subscription(
    profile: TelegramUserProfile,
) -> SubscribeOutcome:
    """提交订阅申请。已订阅 / 待审批 / 已拒绝用户不会重复插入。"""
    async with async_session() as session:
        subscriber = await session.get(Subscriber, profile.user_id)
        if subscriber is not None and subscriber.enabled:
            return SubscribeOutcome(SubscribeResult.ALREADY_SUBSCRIBED)

        pending = await session.get(PendingRequest, profile.user_id)
        if pending is not None:
            pending.username = profile.username
            pending.first_name = profile.first_name
            await session.commit()
            return SubscribeOutcome(SubscribeResult.ALREADY_PENDING)

        denied = await session.get(DeniedUser, profile.user_id)
        if denied is not None:
            return SubscribeOutcome(
                SubscribeResult.DENIED,
                denied_reason=denied.reason,
            )

        session.add(
            PendingRequest(
                user_id=profile.user_id,
                username=profile.username,
                first_name=profile.first_name,
            )
        )
        await session.commit()
        logger.info("subscription requested: user_id=%d", profile.user_id)
        return SubscribeOutcome(SubscribeResult.SUBMITTED)


async def unsubscribe(user_id: int) -> UnsubscribeResult:
    """用户主动取消订阅。

    PROJECT_BRIEF 6.9 要求 /unsubscribe 硬删除订阅者数据，所以这里不做
    enabled=False 的软删除。
    """
    async with async_session() as session:
        subscriber = await session.get(Subscriber, user_id)
        if subscriber is None:
            return UnsubscribeResult.NOT_SUBSCRIBED

        await session.delete(subscriber)
        await session.execute(
            delete(PendingRequest).where(PendingRequest.user_id == user_id)
        )
        await session.commit()
        logger.info("subscription removed by user: user_id=%d", user_id)
        return UnsubscribeResult.UNSUBSCRIBED


async def list_pending_requests() -> list[PendingRequestInfo]:
    """列出所有待审批申请，按申请时间升序。"""
    async with async_session() as session:
        stmt = select(PendingRequest).order_by(PendingRequest.requested_at.asc())
        rows = (await session.execute(stmt)).scalars().all()
        return [
            PendingRequestInfo(
                user_id=row.user_id,
                username=row.username,
                first_name=row.first_name,
                requested_at=row.requested_at,
            )
            for row in rows
        ]


async def approve_request(
    user_id: int,
    approved_by: int,
) -> ApproveOutcome:
    """批准待审批申请，并移动到 subscribers 表。"""
    async with async_session() as session:
        pending = await session.get(PendingRequest, user_id)
        subscriber = await session.get(Subscriber, user_id)

        if pending is None:
            if subscriber is not None and subscriber.enabled:
                return ApproveOutcome(ApproveResult.ALREADY_SUBSCRIBED)
            return ApproveOutcome(ApproveResult.NO_PENDING_REQUEST)

        profile = TelegramUserProfile(
            user_id=pending.user_id,
            username=pending.username,
            first_name=pending.first_name,
        )

        if subscriber is None:
            session.add(
                Subscriber(
                    user_id=pending.user_id,
                    username=pending.username,
                    first_name=pending.first_name,
                    approved_by=approved_by,
                    enabled=True,
                )
            )
        else:
            subscriber.username = pending.username
            subscriber.first_name = pending.first_name
            subscriber.approved_by = approved_by
            subscriber.enabled = True

        await session.delete(pending)
        await session.execute(
            delete(DeniedUser).where(DeniedUser.user_id == user_id)
        )
        await session.commit()
        logger.info(
            "subscription approved: user_id=%d approved_by=%d",
            user_id,
            approved_by,
        )
        return ApproveOutcome(ApproveResult.APPROVED, profile)


async def deny_request(user_id: int, reason: str | None) -> DenyOutcome:
    """拒绝待审批申请，并写入 denied_users 表。"""
    async with async_session() as session:
        pending = await session.get(PendingRequest, user_id)
        subscriber = await session.get(Subscriber, user_id)

        if subscriber is not None and subscriber.enabled:
            return DenyOutcome(DenyResult.ALREADY_SUBSCRIBED)
        if pending is None:
            return DenyOutcome(DenyResult.NO_PENDING_REQUEST)

        profile = TelegramUserProfile(
            user_id=pending.user_id,
            username=pending.username,
            first_name=pending.first_name,
        )
        denied = await session.get(DeniedUser, user_id)
        if denied is None:
            session.add(
                DeniedUser(
                    user_id=pending.user_id,
                    username=pending.username,
                    reason=reason,
                )
            )
        else:
            denied.username = pending.username
            denied.reason = reason

        await session.delete(pending)
        await session.commit()
        logger.info("subscription denied: user_id=%d", user_id)
        return DenyOutcome(DenyResult.DENIED, profile, reason)


async def revoke_subscription(user_id: int) -> RevokeOutcome:
    """管理员撤销订阅。

    与用户主动 /unsubscribe 不同，管理员 revoke 保留 subscriber 行并置
    enabled=False，方便后续审计和重新审批时复用同一个 user_id。
    """
    async with async_session() as session:
        subscriber = await session.get(Subscriber, user_id)
        if subscriber is None or not subscriber.enabled:
            return RevokeOutcome(RevokeResult.NOT_SUBSCRIBED)

        profile = TelegramUserProfile(
            user_id=subscriber.user_id,
            username=subscriber.username,
            first_name=subscriber.first_name,
        )
        subscriber.enabled = False
        await session.commit()
        logger.info("subscription revoked: user_id=%d", user_id)
        return RevokeOutcome(RevokeResult.REVOKED, profile)


async def list_subscribers() -> list[SubscriberInfo]:
    """列出当前 enabled=True 的订阅者。"""
    async with async_session() as session:
        stmt = (
            select(Subscriber)
            .where(Subscriber.enabled.is_(True))
            .order_by(Subscriber.approved_at.asc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [
            SubscriberInfo(
                user_id=row.user_id,
                username=row.username,
                first_name=row.first_name,
                approved_at=row.approved_at,
            )
            for row in rows
        ]
