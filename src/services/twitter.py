"""X (Twitter) 爬虫 service。

依赖 Playwright + 注入 cookies + 拦截 X 自家 GraphQL 响应抓推文。
跟 PROJECT_BRIEF 6.6 节描述一致。

设计：
- TwitterScraper 是 async context manager，封装 browser 生命周期
- scrape_user_timeline() 是主入口，做"抓 + 解析 + 落库"全流程
- 落库用 PostgreSQL UPSERT，指标字段（like/view 等）随重抓更新
"""

import logging
from datetime import datetime, timezone
from types import TracebackType
from typing import Any, Self

from playwright.async_api import (
    Browser,
    BrowserContext,
    Playwright,
    Response,
    async_playwright,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import Tweet, XAuthor
from src.db.session import async_session
from src.services._utils import parse_cookies

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)


class TwitterScraper:
    """封装 Playwright browser 生命周期 + 抓取入口。

    用法：
        async with TwitterScraper() as scraper:
            tweets = await scraper.scrape_user_timeline("whyyoutouzhele")
    """

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> Self:
        self._playwright = await async_playwright().start()
        launch_options: dict[str, Any] = {"headless": True}
        if settings.PLAYWRIGHT_BROWSER_CHANNEL:
            # Windows 本地如遇杀毒软件删除 bundled Chromium，可显式设为 chrome/msedge。
            # Linux Docker 生产不传 channel，使用镜像内安装的 Playwright Chromium。
            launch_options["channel"] = settings.PLAYWRIGHT_BROWSER_CHANNEL
        self._browser = await self._playwright.chromium.launch(**launch_options)
        cookies = parse_cookies(settings.X_SCRAPER_COOKIES)
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
        )
        await self._context.add_cookies(cookies)
        logger.info(
            "playwright browser launched, %d cookies injected", len(cookies)
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        logger.info("playwright browser closed")

    async def scrape_user_timeline(self, screen_name: str) -> list[Tweet]:
        """抓指定 X 博主的当前首页推文，落库，返回 Tweet ORM 对象列表。"""
        if self._context is None:
            raise RuntimeError("TwitterScraper not entered (use 'async with')")

        captured_bodies: list[dict] = []

        async def on_response(response: Response) -> None:
            if "UserTweets" in response.url:
                try:
                    captured_bodies.append(await response.json())
                except Exception:
                    pass

        page = await self._context.new_page()
        page.on("response", on_response)

        url = f"https://x.com/{screen_name}"
        logger.info("scraping %s", url)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # 等异步 GraphQL 调用完成
            await page.wait_for_timeout(8000)
        finally:
            await page.close()

        logger.info(
            "captured %d UserTweets responses", len(captured_bodies)
        )

        parsed: list[dict[str, Any]] = []
        for body in captured_bodies:
            parsed.extend(_extract_tweets(body, screen_name))

        if not parsed:
            logger.warning(
                "no tweets parsed from %s; returning empty list", screen_name
            )
            return []

        # 同一推文可能在多个响应里出现，按 id 去重
        unique: dict[int, dict] = {}
        for p in parsed:
            unique[p["id"]] = p
        parsed = list(unique.values())

        persisted = await _persist_tweets(screen_name, parsed)
        logger.info("persisted %d tweets for %s", len(persisted), screen_name)
        return persisted


# ===================== 解析（pure function，便于测试）=====================

def _extract_tweets(
    body: dict[str, Any], screen_name: str
) -> list[dict[str, Any]]:
    """从 UserTweets GraphQL 响应里挖出 dict 列表。

    返回 dict 而不是 ORM 对象，让解析阶段不依赖 DB session。
    """
    out: list[dict[str, Any]] = []
    try:
        instructions = body["data"]["user"]["result"]["timeline"]["timeline"][
            "instructions"
        ]
    except KeyError:
        return out

    for instr in instructions:
        if instr.get("type") != "TimelineAddEntries":
            continue
        for entry in instr.get("entries", []):
            if not entry.get("entryId", "").startswith("tweet-"):
                continue
            try:
                result = entry["content"]["itemContent"]["tweet_results"][
                    "result"
                ]
                legacy = result.get("legacy")
                if not legacy:
                    continue

                # X 时间格式: 'Sat May 16 09:32:50 +0000 2026'
                posted_at = datetime.strptime(
                    legacy["created_at"], "%a %b %d %H:%M:%S %z %Y"
                )

                media: list[dict[str, Any]] = []
                for m in legacy.get("entities", {}).get("media", []):
                    item: dict[str, Any] = {
                        "type": m.get("type", "unknown"),
                        "url": m.get("media_url_https", ""),
                    }
                    if m.get("type") == "video":
                        variants = m.get("video_info", {}).get("variants", [])
                        if variants:
                            item["video_url"] = variants[-1].get("url", "")
                    media.append(item)

                rest_id = int(result.get("rest_id", "0"))
                out.append({
                    "id": rest_id,
                    "text": legacy.get("full_text", ""),
                    "posted_at": posted_at,
                    "reply_count": legacy.get("reply_count", 0),
                    "like_count": legacy.get("favorite_count", 0),
                    "view_count": int(
                        result.get("views", {}).get("count", "0") or "0"
                    ),
                    "retweet_count": legacy.get("retweet_count", 0),
                    "quote_count": legacy.get("quote_count", 0),
                    "media": media,
                    "permalink": f"https://x.com/{screen_name}/status/{rest_id}",
                    "raw_payload": result,
                })
            except (KeyError, ValueError) as e:
                logger.warning("skipping entry due to parse error: %s", e)
                continue

    return out


# ===================== 落库 =====================

async def _get_or_create_author(
    session: AsyncSession, screen_name: str
) -> XAuthor:
    """按 screen_name 找 XAuthor，不存在就建。返回带 id 的对象。"""
    stmt = select(XAuthor).where(XAuthor.screen_name == screen_name)
    result = await session.execute(stmt)
    author = result.scalar_one_or_none()
    if author is None:
        author = XAuthor(screen_name=screen_name)
        session.add(author)
        await session.flush()  # 让 author.id 立即可用
        logger.info("created XAuthor %s id=%d", screen_name, author.id)
    return author


async def _persist_tweets(
    screen_name: str, tweets_data: list[dict[str, Any]]
) -> list[Tweet]:
    """UPSERT 一批 tweets，已存在的更新 metrics + last_metric_update_at。"""
    async with async_session() as session:
        author = await _get_or_create_author(session, screen_name)

        now = datetime.now(timezone.utc)
        values = [
            {
                **t,
                "author_id": author.id,
                "scraped_at": now,
                "last_metric_update_at": now,
            }
            for t in tweets_data
        ]

        stmt = pg_insert(Tweet).values(values)
        # 已存在的 tweet：更新会变化的字段（指标 + media 可能补充 + raw_payload 留最新）
        # 保留 scraped_at（首次抓取时间不变）
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "reply_count": stmt.excluded.reply_count,
                "like_count": stmt.excluded.like_count,
                "view_count": stmt.excluded.view_count,
                "retweet_count": stmt.excluded.retweet_count,
                "quote_count": stmt.excluded.quote_count,
                "media": stmt.excluded.media,
                "raw_payload": stmt.excluded.raw_payload,
                "last_metric_update_at": stmt.excluded.last_metric_update_at,
            },
        )
        await session.execute(stmt)
        await session.commit()

        # 查回返回（caller 可能要立刻用）
        ids = [t["id"] for t in tweets_data]
        result = await session.execute(select(Tweet).where(Tweet.id.in_(ids)))
        return list(result.scalars().all())
