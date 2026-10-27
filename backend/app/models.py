"""Core tables for phase 1. Every data row carries source_id and fetched_at (core rule 2).
Further tables (news, patterns, forecasts, ...) come with their phases via their own migration."""
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UtcDateTime


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(10), default="user")  # admin | user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))  # price | news | llm | reference
    description: Mapped[str] = mapped_column(Text, default="")
    homepage: Mapped[str] = mapped_column(String(500), default="")
    terms_url: Mapped[str] = mapped_column(String(500), default="")
    update_interval: Mapped[str] = mapped_column(String(100), default="")
    delay_text: Mapped[str] = mapped_column(String(100), default="")
    requires_key: Mapped[bool] = mapped_column(Boolean, default=False)
    is_official: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="disabled")  # online|degraded|offline|disabled
    last_success_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Instrument(Base):
    __tablename__ = "instruments"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    figi: Mapped[str | None] = mapped_column(String(12), nullable=True)
    exchange: Mapped[str] = mapped_column(String(4))  # XNYS | XNAS | XETR
    currency: Mapped[str] = mapped_column(String(3))
    provider_symbols: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    __table_args__ = (UniqueConstraint("symbol", "exchange"),)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class PriceBar(Base):
    __tablename__ = "price_bars"
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(3), primary_key=True)  # 1m|5m|1h|1d
    ts_utc: Mapped[datetime] = mapped_column(UtcDateTime(), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime())
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    price: Mapped[float] = mapped_column(Float)
    change_abs: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ts_utc: Mapped[datetime] = mapped_column(UtcDateTime())
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime())
    delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (Index("ix_quotes_instr_ts", "instrument_id", "ts_utc"),)


class Event(Base):
    """Worker -> API event queue (SQLite-based; Redis possible later)."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(40))  # quote | news | detection | source_status
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class NewsCluster(Base):
    """Merged items about the same story. The UI lists all sources of the cluster."""
    __tablename__ = "news_clusters"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_title: Mapped[str] = mapped_column(String(500))
    first_published_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    last_published_at: Mapped[datetime] = mapped_column(UtcDateTime())
    item_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class NewsItem(Base):
    __tablename__ = "news_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000))
    url_normalized: Mapped[str] = mapped_column(String(1000), index=True)
    title: Mapped[str] = mapped_column(String(500))
    excerpt: Mapped[str] = mapped_column(String(300), default="")  # never the full text
    published_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime())
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id"), index=True)
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)


class NewsInstrument(Base):
    __tablename__ = "news_instruments"
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id"), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True, index=True)
    match_method: Mapped[str] = mapped_column(String(20))  # provider_tag | isin | ticker | name
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class Sentiment(Base):
    """Sentiment per cluster with rationale and method. source_id points to the method
    (sentiment_lexicon or claude_sentiment) and thus appears on the Sources page."""
    __tablename__ = "sentiments"
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id"), primary_key=True)
    label: Mapped[str] = mapped_column(String(10))  # positiv | neutral | negativ
    score: Mapped[float] = mapped_column(Float)  # -1 .. 1
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)  # verbatim quotes
    rationale: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(10))  # lexicon | claude
    model_name: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class LlmUsage(Base):
    """Claude API usage per month (for the hard cap CLAUDE_MONTHLY_BUDGET_USD)."""
    __tablename__ = "llm_usage"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)  # YYYY-MM (UTC)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class AiExplanation(Base):
    """Explanation text for a detection or forecast, generated once per data state (input_hash) and cached.
    method 'claude' = AI text (after validation), 'template' = deterministic template (fallback_reason gives the reason
    if an AI text was attempted and discarded)."""
    __tablename__ = "ai_explanations"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_kind: Mapped[str] = mapped_column(String(10))  # pattern | forecast
    subject_id: Mapped[int] = mapped_column(Integer)
    input_hash: Mapped[str] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    __table_args__ = (UniqueConstraint("subject_kind", "subject_id", "input_hash"),)


class IndicatorEvent(Base):
    """Indicator event with explanation (criteria with actual values). source_id is the source of the
    marker candle, source_ids all sources of the candles used; fetched_at the latest retrieval of them."""
    __tablename__ = "indicator_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    timeframe: Mapped[str] = mapped_column(String(3))
    # golden_cross | death_cross | rsi_divergence | bb_breakout | volume_spike
    type: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(4), default="none")  # up | down | none
    ts_utc: Mapped[datetime] = mapped_column(UtcDateTime())
    start_ts: Mapped[datetime] = mapped_column(UtcDateTime())
    end_ts: Mapped[datetime] = mapped_column(UtcDateTime())
    confirmed_at: Mapped[datetime] = mapped_column(UtcDateTime())
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    values: Mapped[dict[str, Any]] = mapped_column(JSON)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    algo_version: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    source_ids: Mapped[list[int]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime())
    detected_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("instrument_id", "timeframe", "type", "direction", "ts_utc", "algo_version"),
        Index("ix_indicator_events_lookup", "instrument_id", "timeframe", "ts_utc"),
    )


class NotableMove(Base):
    """Notable price move (return or volume z-value above threshold)."""
    __tablename__ = "notable_moves"
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    timeframe: Mapped[str] = mapped_column(String(3))
    move_start: Mapped[datetime] = mapped_column(UtcDateTime())
    move_end: Mapped[datetime] = mapped_column(UtcDateTime())
    return_pct: Mapped[float] = mapped_column(Float)
    return_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasons: Mapped[list[str]] = mapped_column(JSON)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    algo_version: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    source_ids: Mapped[list[int]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime())
    detected_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("instrument_id", "timeframe", "move_start", "algo_version"),)


class MoveNewsLink(Base):
    """Temporal coincidence move <-> news cluster. No statement about cause."""
    __tablename__ = "move_news_links"
    move_id: Mapped[int] = mapped_column(ForeignKey("notable_moves.id", ondelete="CASCADE"), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id"), primary_key=True)
    time_offset_minutes: Mapped[int] = mapped_column(Integer)  # publication minus start of the candle
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
class ApiUsage(Base):
    """Retrieval counter per source and UTC day for daily quotas (survives worker restarts)."""
    __tablename__ = "api_usage"
    source_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)


class SentimentBatch(Base):
    """A batch request for sentiments submitted to Anthropic. reserved_usd is the maximum amount counted against the
    monthly limit until the results arrive."""
    __tablename__ = "sentiment_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(15), default="in_progress")  # in_progress | ended
    reserved_usd: Mapped[float] = mapped_column(Float, default=0.0)
    submitted_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)


class SentimentBatchItem(Base):
    __tablename__ = "sentiment_batch_items"
    batch_id: Mapped[int] = mapped_column(ForeignKey("sentiment_batches.id"), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id"), primary_key=True, index=True)
    # pending | succeeded | rejected (response not verifiable) | errored | expired | canceled
    status: Mapped[str] = mapped_column(String(10), default="pending")


class PatternDetection(Base):
    """Detected chart pattern with full explanation (core rule 3): criteria with actual values,
    confidence breakdown, scenarios with levels. The hit rate hangs on the backtest (backtest_runs) and is looked up
    on reading. source_id is the source of the last pattern candle, source_ids all those used."""
    __tablename__ = "pattern_detections"
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    timeframe: Mapped[str] = mapped_column(String(3))
    pattern_type: Mapped[str] = mapped_column(String(30))
    fingerprint: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    direction: Mapped[str] = mapped_column(String(10))  # aufwärts | abwärts | offen
    start_ts: Mapped[datetime] = mapped_column(UtcDateTime())
    end_ts: Mapped[datetime] = mapped_column(UtcDateTime())
    formed_ts: Mapped[datetime] = mapped_column(UtcDateTime())
    status: Mapped[str] = mapped_column(String(12))  # in_bildung | bestaetigt | ungueltig
    status_reason: Mapped[str] = mapped_column(Text, default="")
    status_changed_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    breakout_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    key_points: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    confirmation_level: Mapped[float] = mapped_column(Float)
    invalidation_level: Mapped[float] = mapped_column(Float)
    scenarios: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    params_hash: Mapped[str] = mapped_column(String(16))
    algo_version: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    source_ids: Mapped[list[int]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime())
    detected_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("instrument_id", "timeframe", "fingerprint"),
        Index("ix_pattern_detections_lookup", "instrument_id", "timeframe", "end_ts"),
    )


class SupportResistanceZone(Base):
    """Support/resistance zone from clusters of turning points; replaced completely on every run."""
    __tablename__ = "sr_zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    timeframe: Mapped[str] = mapped_column(String(3))
    kind: Mapped[str] = mapped_column(String(15))  # unterstuetzung | widerstand | im_bereich
    lower: Mapped[float] = mapped_column(Float)
    upper: Mapped[float] = mapped_column(Float)
    touches: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    first_touch: Mapped[datetime] = mapped_column(UtcDateTime())
    last_touch: Mapped[datetime] = mapped_column(UtcDateTime())
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text)
    params_hash: Mapped[str] = mapped_column(String(16))
    algo_version: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    source_ids: Mapped[list[int]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime())
    computed_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class PatternScan(Base):
    """Last run of the pattern detection per instrument and timeframe: data basis (core rule 2) and
    reason for being empty (core rule 6)."""
    __tablename__ = "pattern_scans"
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(3), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    bars_from: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    bars_to: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    recent_from: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    bar_count: Mapped[int] = mapped_column(Integer, default=0)
    last_fetched_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    source_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    params_hash: Mapped[str] = mapped_column(String(16))
    algo_version: Mapped[str] = mapped_column(String(20))
    empty_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class BacktestRun(Base):
    """Result of a backtest (workstream 3C writes, 3B reads). For patterns: kind='pattern',
    subject=pattern_type; the latest run with the same timeframe and algo_version applies."""
    __tablename__ = "backtest_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # pattern | forecast
    subject: Mapped[str] = mapped_column(String(50))
    timeframe: Mapped[str] = mapped_column(String(3))
    algo_version: Mapped[str] = mapped_column(String(20))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    universe: Mapped[str] = mapped_column(Text, default="")
    date_range: Mapped[str] = mapped_column(String(100), default="")
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    hit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    code_version: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    __table_args__ = (Index("ix_backtest_runs_lookup", "kind", "subject", "timeframe", "algo_version", "created_at"),)


class Forecast(Base):
    """Latest forecast per instrument, timeframe and method (core rule 4: only quantiles per step).
    backtest_run_id points to the forecast backtest (backtest_runs, kind='forecast'). pattern_levels contains
    for the main method the simulated shares with which pattern levels are reached first."""
    __tablename__ = "forecasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    timeframe: Mapped[str] = mapped_column(String(3))
    method: Mapped[str] = mapped_column(String(40))
    horizon: Mapped[int] = mapped_column(Integer, default=0)
    based_on_until: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    last_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    params_hash: Mapped[str] = mapped_column(String(16))
    algo_version: Mapped[str] = mapped_column(String(20))
    inputs_hash: Mapped[str] = mapped_column(String(64), default="")
    backtest_run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    backtest_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    pattern_levels: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Main method only: a few simulated paths as examples (analysis.forecast.example_path_rows)
    example_paths: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    bars_from: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    bar_count: Mapped[int] = mapped_column(Integer, default=0)
    source_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    fetched_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    empty_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    __table_args__ = (UniqueConstraint("instrument_id", "timeframe", "method"),)
