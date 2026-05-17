"""AI 成本查询 service。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from src.db.models import AiCallLog
from src.db.session import async_session


@dataclass(frozen=True)
class AiCostSummary:
    days: int
    call_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


async def summarize_ai_cost(days: int) -> AiCostSummary:
    """汇总近 N 天 AI 调用成本。"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with async_session() as session:
        stmt = select(
            func.count(AiCallLog.id),
            func.coalesce(func.sum(AiCallLog.input_tokens), 0),
            func.coalesce(func.sum(AiCallLog.output_tokens), 0),
            func.coalesce(func.sum(AiCallLog.cost_usd), 0),
        ).where(AiCallLog.created_at >= since)
        row = (await session.execute(stmt)).one()

    return AiCostSummary(
        days=days,
        call_count=int(row[0]),
        input_tokens=int(row[1]),
        output_tokens=int(row[2]),
        cost_usd=Decimal(row[3]),
    )
