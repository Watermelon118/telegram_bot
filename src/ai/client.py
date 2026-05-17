"""OpenAI 调用封装。

所有 service 层访问 OpenAI 都走这里，理由：
- 统一重试 / 超时策略
- 统一 token 统计 → 落 ai_call_log（成本追踪）
- 换模型 / 加缓存 / A-B 只改这一处
- 测试时 mock 这一层就够，不用 mock SDK

设计要点：
- AsyncOpenAI 单例，进程内共享（SDK 内部连接池）
- complete() 是主入口；调用方传 purpose + model + messages
- 重试：指数退避 3 次；只在网络/超时/限流类错误重试，业务错误（认证、参数）立刻抛
- 价格表硬编码在本文件常量里；价格变动时同步 PROJECT_BRIEF.md 的 5.5 节
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError
from openai.types.chat import ChatCompletionMessageParam
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import AiCallLog
from src.db.session import async_session

logger = logging.getLogger(__name__)


# 价格表：USD / 1M tokens。来源：OpenAI 官网 pricing 页（2026-05 抓取）。
# 变动时同步本表 + commit message 注明。
_PRICING_USD_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    # (input, output)
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}

_MAX_RETRIES = 3
_INITIAL_BACKOFF_SECONDS = 1.0
_REQUEST_TIMEOUT_SECONDS = 60.0

# 进程内 client 单例；首次访问时才建（让 import 不依赖 OPENAI_API_KEY）
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY not set; add it to .env before calling AI"
            )
        _client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    return _client


@dataclass
class AiResult:
    """一次 AI 调用的结果，含正文 + 统计字段。"""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int


def _calc_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """按价格表算 USD 成本。价格表没有的模型回 0 + warn（不阻塞业务）。"""
    pricing = _PRICING_USD_PER_1M_TOKENS.get(model)
    if pricing is None:
        logger.warning("no pricing for model %s; cost recorded as 0", model)
        return 0.0
    input_price, output_price = pricing
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


async def complete(
    purpose: str,
    model: str,
    messages: list[ChatCompletionMessageParam],
    *,
    temperature: float = 0.3,
    max_output_tokens: int | None = None,
) -> AiResult:
    """调 OpenAI Chat Completion，带重试和 ai_call_log 落库。

    参数：
        purpose: 业务用途标签（'per_tweet_summary' / 'overall_takeaway' / ...）
                 仅用于日志和成本追踪，不影响调用本身
        model: OpenAI 模型 id（必须在 _PRICING 表里有，否则成本记 0）
        messages: 标准 chat 消息列表
        temperature: 默认 0.3，摘要类任务想稳一点
        max_output_tokens: 输出 token 上限；None 走 SDK 默认

    返回：AiResult（text + 统计字段）

    抛出：
        - 重试 3 次仍失败的网络/超时/限流 → 抛原始 OpenAI 异常
        - 业务错误（401/400 等）→ 立刻抛，不重试
    """
    client = _get_client()
    last_exc: Exception | None = None
    started_at = time.monotonic()

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            kwargs: dict = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_output_tokens is not None:
                kwargs["max_completion_tokens"] = max_output_tokens

            resp = await client.chat.completions.create(**kwargs)

            duration_ms = int((time.monotonic() - started_at) * 1000)
            text = (resp.choices[0].message.content or "").strip()
            usage = resp.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0
            cost_usd = _calc_cost_usd(model, input_tokens, output_tokens)

            await _record_log(
                purpose=purpose,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
                success=True,
                error_message=None,
            )

            logger.info(
                "ai call ok purpose=%s model=%s in=%d out=%d cost=$%.6f dur=%dms",
                purpose, model, input_tokens, output_tokens, cost_usd, duration_ms,
            )
            return AiResult(
                text=text,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
            )

        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_exc = e
            if attempt == _MAX_RETRIES:
                break
            backoff = _INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "ai call %s/%s failed (%s), retrying in %.1fs: %s",
                attempt, _MAX_RETRIES, type(e).__name__, backoff, e,
            )
            await asyncio.sleep(backoff)

        except Exception as e:
            # 非重试型错误（认证、参数等）：立刻记日志 + 抛
            duration_ms = int((time.monotonic() - started_at) * 1000)
            await _record_log(
                purpose=purpose,
                model=model,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                duration_ms=duration_ms,
                success=False,
                error_message=f"{type(e).__name__}: {e}",
            )
            logger.error("ai call non-retriable error purpose=%s: %s", purpose, e)
            raise

    # 重试用尽
    duration_ms = int((time.monotonic() - started_at) * 1000)
    await _record_log(
        purpose=purpose,
        model=model,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        duration_ms=duration_ms,
        success=False,
        error_message=f"{type(last_exc).__name__}: {last_exc}",
    )
    logger.error(
        "ai call exhausted retries purpose=%s model=%s: %s",
        purpose, model, last_exc,
    )
    assert last_exc is not None
    raise last_exc


async def _record_log(
    *,
    purpose: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    duration_ms: int,
    success: bool,
    error_message: str | None,
    session: AsyncSession | None = None,
) -> None:
    """写一行 ai_call_log。session 不传时自起一个 + commit。"""
    row = AiCallLog(
        purpose=purpose,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
        success=success,
        error_message=error_message,
    )
    if session is not None:
        session.add(row)
        return
    async with async_session() as s:
        s.add(row)
        await s.commit()
