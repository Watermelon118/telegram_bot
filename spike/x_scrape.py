"""
Spike v3: Playwright + cookies 抓 X 推文，完整解析 + 头条选择验证。

策略：
1. headless Chromium + 注入 cookies
2. 访问目标用户主页
3. 拦截 X 自家的 UserTweets GraphQL 响应
4. 从 JSON 里挖出 Tweet 对象
5. 按"评论+点赞+浏览"分数选头条

Run: uv run spike/x_scrape.py
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime

from dotenv import load_dotenv
from playwright.async_api import Response, async_playwright

TARGET_USERNAME = "whyyoutouzhele"


@dataclass
class Tweet:
    id: str
    text: str
    posted_at: datetime
    likes: int
    retweets: int
    replies: int
    quotes: int
    views: int
    media: list[dict] = field(default_factory=list)
    permalink: str = ""

    @property
    def engagement_score(self) -> int:
        """头条规则：评论 + 点赞 + 浏览"""
        return self.replies + self.likes + self.views


def parse_cookies(cookies_str: str, domain: str = ".x.com") -> list[dict]:
    cookies = []
    for pair in cookies_str.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        cookies.append({"name": name.strip(), "value": value.strip(), "domain": domain, "path": "/"})
    return cookies


def extract_tweets(body: dict) -> list[Tweet]:
    """从 UserTweets GraphQL 响应里挖出 Tweet 列表。失败 silent skip。"""
    tweets: list[Tweet] = []
    try:
        instructions = body["data"]["user"]["result"]["timeline"]["timeline"]["instructions"]
    except KeyError:
        return tweets

    for instr in instructions:
        if instr.get("type") != "TimelineAddEntries":
            continue
        for entry in instr.get("entries", []):
            if not entry.get("entryId", "").startswith("tweet-"):
                continue
            try:
                result = entry["content"]["itemContent"]["tweet_results"]["result"]
                legacy = result.get("legacy")
                if not legacy:
                    continue

                # X 时间格式: 'Sat May 16 09:32:50 +0000 2026'
                posted_at = datetime.strptime(
                    legacy["created_at"], "%a %b %d %H:%M:%S %z %Y"
                )

                media = []
                for m in legacy.get("entities", {}).get("media", []):
                    item = {
                        "type": m.get("type", "unknown"),
                        "url": m.get("media_url_https", ""),
                    }
                    if m.get("type") == "video":
                        variants = m.get("video_info", {}).get("variants", [])
                        if variants:
                            # 最后一个一般是最高码率
                            item["video_url"] = variants[-1].get("url", "")
                    media.append(item)

                rest_id = result.get("rest_id", "")
                screen_name = (
                    result.get("core", {})
                    .get("user_results", {})
                    .get("result", {})
                    .get("legacy", {})
                    .get("screen_name", TARGET_USERNAME)
                )

                tweets.append(Tweet(
                    id=rest_id,
                    text=legacy.get("full_text", ""),
                    posted_at=posted_at,
                    likes=legacy.get("favorite_count", 0),
                    retweets=legacy.get("retweet_count", 0),
                    replies=legacy.get("reply_count", 0),
                    quotes=legacy.get("quote_count", 0),
                    views=int(result.get("views", {}).get("count", "0") or "0"),
                    media=media,
                    permalink=f"https://x.com/{screen_name}/status/{rest_id}",
                ))
            except (KeyError, ValueError) as e:
                print(f"  [parse warning] skip entry: {e}")
                continue

    return tweets


async def main() -> None:
    load_dotenv()
    cookies = parse_cookies(os.environ["X_SCRAPER_COOKIES"])
    print(f"loaded {len(cookies)} cookies")

    captured_bodies: list[dict] = []

    async with async_playwright() as p:
        # channel="chrome" 让 Playwright 用系统装的 Google Chrome，
        # 避免 Playwright 自带 Chromium 被火绒/Defender 删
        browser = await p.chromium.launch(headless=True, channel="chrome")
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        await context.add_cookies(cookies)
        page = await context.new_page()

        async def on_response(response: Response) -> None:
            if "UserTweets" in response.url:
                try:
                    captured_bodies.append(await response.json())
                except Exception:
                    pass

        page.on("response", on_response)

        url = f"https://x.com/{TARGET_USERNAME}"
        print(f"navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        print("waiting for tweets to load...")
        await page.wait_for_timeout(8000)

        await browser.close()

    print(f"\ncaptured {len(captured_bodies)} UserTweets responses")

    # 解析 + 按 id 去重 + 按时间倒序
    all_tweets: list[Tweet] = []
    for body in captured_bodies:
        all_tweets.extend(extract_tweets(body))

    seen: set[str] = set()
    unique: list[Tweet] = []
    for t in all_tweets:
        if t.id not in seen:
            seen.add(t.id)
            unique.append(t)
    unique.sort(key=lambda t: t.posted_at, reverse=True)

    print(f"\n========== parsed {len(unique)} unique tweets ==========\n")
    for i, t in enumerate(unique, 1):
        print(f"--- [{i}] id={t.id} ---")
        print(f"posted:  {t.posted_at.isoformat()}")
        print(f"text:    {t.text[:120]}")
        print(f"metrics: likes={t.likes} rt={t.retweets} replies={t.replies} views={t.views}")
        print(f"score:   {t.engagement_score}")
        if t.media:
            kinds = ",".join(m["type"] for m in t.media)
            print(f"media:   {len(t.media)} ({kinds})")
        print(f"link:    {t.permalink}")
        print()

    if unique:
        featured = max(unique, key=lambda t: t.engagement_score)
        print(f"========== FEATURED (头条) ==========")
        print(f"id:    {featured.id}")
        print(f"score: {featured.engagement_score}")
        print(f"text:  {featured.text[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
