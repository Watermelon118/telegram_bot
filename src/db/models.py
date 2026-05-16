"""SQLAlchemy 2.0 ORM 模型，对应 PROJECT_BRIEF.md 第 5 节的 8 张表。

设计原则：
- 所有时间用 TIMESTAMP WITH TIME ZONE（TIMESTAMPTZ），由 Postgres 服务端 default NOW()
- 计数器字段服务端 DEFAULT 0，避免应用层忘记初始化
- ForeignKey 显式声明 ondelete 行为，未声明的默认 NO ACTION
- JSONB 存半结构化数据（媒体列表、原始 payload 等）
- Python 类型注解尽量精确：用 `int | None` 表示可空，SQLAlchemy 自动推断 nullable
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """所有模型的基类。"""


# ---------- X 博主元数据 ----------

class XAuthor(Base):
    __tablename__ = "x_authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    screen_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128))
    user_id_x: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    tweets: Mapped[list["Tweet"]] = relationship(back_populates="author")
    digests: Mapped[list["DailyDigest"]] = relationship(back_populates="author")


# ---------- 抓到的推文 ----------

class Tweet(Base):
    __tablename__ = "tweets"

    # X 平台的 tweet id（snowflake，本身就是 BigInt 主键，天然去重）
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    author_id: Mapped[int] = mapped_column(
        ForeignKey("x_authors.id", ondelete="CASCADE"), index=True
    )

    text: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), index=True
    )

    reply_count: Mapped[int] = mapped_column(server_default="0")
    like_count: Mapped[int] = mapped_column(server_default="0")
    view_count: Mapped[int] = mapped_column(server_default="0")
    retweet_count: Mapped[int] = mapped_column(server_default="0")
    quote_count: Mapped[int] = mapped_column(server_default="0")

    # [{type:'photo'|'video'|'gif', url:'...', video_url:'...'}]
    media: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    permalink: Mapped[str | None] = mapped_column(String(500))
    # 原始抓取数据，留底，方便 schema 变更时回填
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    scraped_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    last_metric_update_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    author: Mapped[XAuthor] = relationship(back_populates="tweets")


# ---------- 每日推送摘要 ----------

class DailyDigest(Base):
    __tablename__ = "daily_digests"
    __table_args__ = (
        UniqueConstraint("digest_date", "author_id", name="uq_digest_date_author"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_date: Mapped[date] = mapped_column(Date)  # NZ 时区日期
    author_id: Mapped[int] = mapped_column(ForeignKey("x_authors.id"))

    featured_tweet_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tweets.id")
    )
    # 当日其他推文 id 列表
    other_tweet_ids: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    # {tweet_id: "一句话摘要"}
    summary_per_tweet: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    # "整体看点" 2-3 句
    overall_takeaway: Mapped[str | None] = mapped_column(Text)

    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    model_used: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]

    author: Mapped[XAuthor] = relationship(back_populates="digests")


# ---------- 订阅者 ----------

class Subscriber(Base):
    __tablename__ = "subscribers"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))

    approved_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    approved_by: Mapped[int | None] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    last_pushed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


# ---------- 待审批申请 ----------

class PendingRequest(Base):
    __tablename__ = "pending_requests"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    requested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


# ---------- 拒绝记录 ----------

class DeniedUser(Base):
    __tablename__ = "denied_users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    denied_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    reason: Mapped[str | None] = mapped_column(Text)


# ---------- 推送历史 ----------

class PushHistory(Base):
    __tablename__ = "push_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_id: Mapped[int | None] = mapped_column(ForeignKey("daily_digests.id"))
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subscribers.user_id", ondelete="CASCADE")
    )
    sent_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    success: Mapped[bool] = mapped_column(Boolean, server_default="true")
    error_message: Mapped[str | None] = mapped_column(Text)


# ---------- AI 调用日志（成本追踪） ----------

class AiCallLog(Base):
    __tablename__ = "ai_call_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 'per_tweet_summary' / 'overall_takeaway' / 'featured_analysis' / ...
    purpose: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    # 按调用时模型价格表算好，避免历史价格变了对不上
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    duration_ms: Mapped[int | None]
    success: Mapped[bool] = mapped_column(Boolean, server_default="true")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
