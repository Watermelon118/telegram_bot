"""每日 digest 编排 service。

职责：把"当日推文"组装成可推送的内容包，落库 daily_digests 表。

流程：
1. 查当日（NZ 时区）该博主所有推文
2. 选头条：reply + like + view 三者之和最大的一条
3. 对其余推文跑 per-tweet 摘要（并发）
4. 综合摘要 → 整体看点（单次强模型调用）
5. UPSERT daily_digests 表
6. 返回 DigestPackage 给上层（handler / push）

"要闻"段范围（2026-05-17 收紧）：
- 按"热度（reply+like+view）"排序后取 **第 2-6 名共 5 条**
- 排名 7+ 的不进 digest（不摘要、不入库 other_tweet_ids、不展示）
- 理由：用户只关心热度高的，AI 调用成本也从 ~20 次砍到 6 次

边界情况：
- 当日 0 条推：返回 empty package，不落库（无意义）
- 当日 1 条推：那条就是头条，不跑 AI（省钱），不落 summary/takeaway
- 当日 2-6 条推：全部 -1（除头条外）进要闻
- AI 部分失败：summary 单条失败用占位串；takeaway 整体失败用占位串。不抛
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import DailyDigest, Tweet, XAuthor
from src.db.session import async_session
from src.services import summary

logger = logging.getLogger(__name__)

# "今日要闻"段最多展示 N 条（按热度排名 2 到 N+1）。
# 热度 = reply + like + view。排名超 N+1 的丢弃。
_BRIEFS_MAX_COUNT = 5


@dataclass
class DigestPackage:
    """完整的 digest 内容包，handler / push 直接消费。"""

    digest_date: date
    author_screen_name: str
    featured: Tweet | None  # None = 当日 0 条推
    others: list[Tweet]      # 按 posted_at 倒序
    summary_per_tweet: dict[int, str]  # 只覆盖 others 里的推文
    overall_takeaway: str | None        # None = 0 或 1 条推时不生成
    digest_id: int | None               # 落库后的 daily_digests.id；0 条推时为 None


async def generate_digest(
    screen_name: str,
    target_date: date | None = None,
) -> DigestPackage:
    """生成指定博主指定日期的 digest。

    target_date: 默认今天（NZ 时区）。传日期可以补跑历史。
    """
    tz = ZoneInfo(settings.TIMEZONE)
    if target_date is None:
        target_date = datetime.now(tz).date()

    # 时间窗：NZ 当日 00:00 → 24:00（按 posted_at 转 NZ 时区过滤）
    # 生产路径会在 NZ 19:30 触发，那时 00:00-now ≈ 00:00-20:00，符合 brief 2.1
    # /digest 用户手动触发任何时间都能跑，比 brief 写死 00:00-20:00 灵活
    window_start = datetime.combine(target_date, time(0, 0), tzinfo=tz)
    window_end = datetime.combine(target_date, time(23, 59, 59), tzinfo=tz)
    # 入库都是 UTC，比较时转 UTC（其实 TIMESTAMPTZ 跨时区比较 PG 会自动处理，
    # 但显式 utc 让 SQL 更直观）
    window_start_utc = window_start.astimezone(timezone.utc)
    window_end_utc = window_end.astimezone(timezone.utc)

    async with async_session() as session:
        author = await _get_author(session, screen_name)
        if author is None:
            logger.warning(
                "no XAuthor row for %s; scraper hasn't run yet?", screen_name
            )
            return _empty_package(target_date, screen_name)

        tweets = await _query_tweets(
            session, author.id, window_start_utc, window_end_utc
        )

    logger.info(
        "digest for %s @ %s: %d tweets in window",
        screen_name, target_date, len(tweets),
    )

    if not tweets:
        return _empty_package(target_date, screen_name)

    # 按热度排序（reply + like + view）→ 第 1 名头条，第 2 到 _BRIEFS_MAX_COUNT+1 名进要闻
    def _score(t: Tweet) -> int:
        return (t.reply_count or 0) + (t.like_count or 0) + (t.view_count or 0)

    by_heat = sorted(tweets, key=_score, reverse=True)
    featured = by_heat[0]
    others = by_heat[1 : 1 + _BRIEFS_MAX_COUNT]
    logger.info(
        "digest selection: featured=%d (score=%d), briefs=%d (of %d total tweets, dropped %d cold ones)",
        featured.id, _score(featured), len(others), len(tweets),
        max(0, len(tweets) - 1 - _BRIEFS_MAX_COUNT),
    )

    # 单条推：跳过 AI，省钱
    if not others:
        digest_id = await _upsert_digest(
            digest_date=target_date,
            author_id=author.id,
            featured_tweet_id=featured.id,
            other_tweet_ids=[],
            summary_per_tweet={},
            overall_takeaway=None,
            model_used=None,
            input_tokens=0,
            output_tokens=0,
        )
        return DigestPackage(
            digest_date=target_date,
            author_screen_name=screen_name,
            featured=featured,
            others=[],
            summary_per_tweet={},
            overall_takeaway=None,
            digest_id=digest_id,
        )

    # 多条：跑 per-tweet 摘要 + 整体看点
    per_tweet_input = [(t.id, t.text) for t in others]
    summary_map = await summary.summarize_per_tweet(per_tweet_input)
    takeaway = await summary.generate_overall_takeaway(
        list(summary_map.values())
    )

    # ai_call_log 里 token 已落，digest 表也记一份汇总值方便后续 admin 查
    # 因为 client 没把单次结果回灌到 service，简化处理：写 0 + model 标识
    # （想精确统计直接 SELECT SUM FROM ai_call_log WHERE created_at...）
    digest_id = await _upsert_digest(
        digest_date=target_date,
        author_id=author.id,
        featured_tweet_id=featured.id,
        other_tweet_ids=[t.id for t in others],
        summary_per_tweet={str(k): v for k, v in summary_map.items()},
        overall_takeaway=takeaway,
        model_used=f"{settings.MODEL_PER_TWEET}+{settings.MODEL_OVERALL}",
        input_tokens=0,
        output_tokens=0,
    )

    return DigestPackage(
        digest_date=target_date,
        author_screen_name=screen_name,
        featured=featured,
        others=others,
        summary_per_tweet=summary_map,
        overall_takeaway=takeaway,
        digest_id=digest_id,
    )


async def load_digest(
    screen_name: str,
    target_date: date | None = None,
) -> DigestPackage | None:
    """从 daily_digests 读取已生成的 digest。

    用途：19:30 生成 digest，20:00 推送时复用，避免重复 AI 调用。
    返回 None 表示当天还没有生成过。
    """
    tz = ZoneInfo(settings.TIMEZONE)
    if target_date is None:
        target_date = datetime.now(tz).date()

    async with async_session() as session:
        author = await _get_author(session, screen_name)
        if author is None:
            return None

        stmt = select(DailyDigest).where(
            DailyDigest.digest_date == target_date,
            DailyDigest.author_id == author.id,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None

        featured = None
        if row.featured_tweet_id is not None:
            featured = await session.get(Tweet, row.featured_tweet_id)

        other_ids = row.other_tweet_ids or []
        others_by_id: dict[int, Tweet] = {}
        if other_ids:
            tweets_stmt = select(Tweet).where(Tweet.id.in_(other_ids))
            tweets = (await session.execute(tweets_stmt)).scalars().all()
            others_by_id = {t.id: t for t in tweets}

        summary_map = {
            int(tweet_id): summary_text
            for tweet_id, summary_text in (row.summary_per_tweet or {}).items()
        }

        return DigestPackage(
            digest_date=target_date,
            author_screen_name=screen_name,
            featured=featured,
            others=[others_by_id[i] for i in other_ids if i in others_by_id],
            summary_per_tweet=summary_map,
            overall_takeaway=row.overall_takeaway,
            digest_id=row.id,
        )


async def get_or_generate_digest(
    screen_name: str,
    target_date: date | None = None,
) -> DigestPackage:
    """优先复用已生成 digest，不存在时再生成。"""
    loaded = await load_digest(screen_name, target_date)
    if loaded is not None:
        return loaded
    return await generate_digest(screen_name, target_date)


# ===================== 辅助 =====================

def _empty_package(d: date, screen_name: str) -> DigestPackage:
    return DigestPackage(
        digest_date=d,
        author_screen_name=screen_name,
        featured=None,
        others=[],
        summary_per_tweet={},
        overall_takeaway=None,
        digest_id=None,
    )


async def _get_author(
    session: AsyncSession, screen_name: str
) -> XAuthor | None:
    stmt = select(XAuthor).where(XAuthor.screen_name == screen_name)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _query_tweets(
    session: AsyncSession,
    author_id: int,
    start_utc: datetime,
    end_utc: datetime,
) -> list[Tweet]:
    stmt = (
        select(Tweet)
        .where(Tweet.author_id == author_id)
        .where(Tweet.posted_at >= start_utc)
        .where(Tweet.posted_at <= end_utc)
        .order_by(Tweet.posted_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _upsert_digest(
    *,
    digest_date: date,
    author_id: int,
    featured_tweet_id: int | None,
    other_tweet_ids: list[int],
    summary_per_tweet: dict[str, str],
    overall_takeaway: str | None,
    model_used: str | None,
    input_tokens: int,
    output_tokens: int,
) -> int:
    """UPSERT daily_digests by (digest_date, author_id)，返回行 id。"""
    async with async_session() as session:
        stmt = pg_insert(DailyDigest).values(
            digest_date=digest_date,
            author_id=author_id,
            featured_tweet_id=featured_tweet_id,
            other_tweet_ids=other_tweet_ids,
            summary_per_tweet=summary_per_tweet,
            overall_takeaway=overall_takeaway,
            model_used=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        # 重跑同一天 digest（/digest 反复调用、或当日补跑）→ 覆盖
        stmt = stmt.on_conflict_do_update(
            constraint="uq_digest_date_author",
            set_={
                "featured_tweet_id": stmt.excluded.featured_tweet_id,
                "other_tweet_ids": stmt.excluded.other_tweet_ids,
                "summary_per_tweet": stmt.excluded.summary_per_tweet,
                "overall_takeaway": stmt.excluded.overall_takeaway,
                "model_used": stmt.excluded.model_used,
                "input_tokens": stmt.excluded.input_tokens,
                "output_tokens": stmt.excluded.output_tokens,
                "generated_at": datetime.now(timezone.utc),
            },
        ).returning(DailyDigest.id)
        result = await session.execute(stmt)
        digest_id = result.scalar_one()
        await session.commit()
        return digest_id
