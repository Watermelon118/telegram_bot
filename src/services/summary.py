"""摘要 service：把推文列表转成"每条一句话" + "整体看点"。

为什么单独一层 service：
- handler / digest 不需要知道用哪个 prompt、哪个模型
- 业务规则（per tweet 用便宜模型，takeaway 用强模型）在这里集中
- 单条失败不能拖垮整批：per-tweet 并发跑，单条挂了占位 "[摘要失败]"
"""

import asyncio
import logging

from src.ai import client, prompts
from src.config import settings

logger = logging.getLogger(__name__)


# 并发上限，避免一次几十条推文把 OpenAI rate limit 打爆
_PER_TWEET_CONCURRENCY = 5


async def summarize_per_tweet(
    tweets: list[tuple[int, str]],
) -> dict[int, str]:
    """对每条推文跑一句话摘要。

    输入：[(tweet_id, tweet_text), ...]
    返回：{tweet_id: "一句话摘要"}（失败的条目摘要为 "[摘要失败]"）

    并发跑（受 _PER_TWEET_CONCURRENCY 限制）。
    """
    if not tweets:
        return {}

    sem = asyncio.Semaphore(_PER_TWEET_CONCURRENCY)

    async def one(tweet_id: int, text: str) -> tuple[int, str]:
        async with sem:
            try:
                result = await client.complete(
                    purpose="per_tweet_summary",
                    model=settings.MODEL_PER_TWEET,
                    messages=prompts.per_tweet_summary(text),
                    max_output_tokens=80,
                )
                return tweet_id, result.text
            except Exception as e:
                logger.error(
                    "per-tweet summary failed for tweet_id=%d: %s", tweet_id, e
                )
                return tweet_id, "[摘要失败]"

    results = await asyncio.gather(
        *(one(tid, txt) for tid, txt in tweets), return_exceptions=False
    )
    return dict(results)


async def generate_overall_takeaway(per_tweet_summaries: list[str]) -> str:
    """综合所有一句话摘要 → 2-3 句整体看点。

    失败时返回占位串，让上层不至于整个 digest 挂掉。
    """
    valid = [s for s in per_tweet_summaries if s and s != "[摘要失败]"]
    if not valid:
        return "[今日整体看点生成失败：所有推文摘要均失败]"

    try:
        result = await client.complete(
            purpose="overall_takeaway",
            model=settings.MODEL_OVERALL,
            messages=prompts.overall_takeaway(valid),
            max_output_tokens=300,
        )
        return result.text
    except Exception as e:
        logger.error("overall takeaway failed: %s", e)
        return "[今日整体看点生成失败]"
