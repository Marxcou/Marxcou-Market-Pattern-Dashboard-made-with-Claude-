"""Load candles: exactly one candle per timestamp (for 1d per calendar day), preferably by SOURCE_PRIORITY.
Shared by /bars and the analyses so both see the same candles."""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.moves import TIMEFRAME_DELTA
from app.models import PriceBar, Source
from app.price_service import SOURCE_PRIORITY


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def load_bars(db: Session, instrument_id: int, timeframe: str, start: datetime | None = None,
              end: datetime | None = None, limit: int = 2000) -> list[tuple[PriceBar, Source]]:
    stmt = (select(PriceBar, Source).join(Source, Source.id == PriceBar.source_id)
            .where(PriceBar.instrument_id == instrument_id, PriceBar.timeframe == timeframe))
    if start:
        stmt = stmt.where(PriceBar.ts_utc >= start)
    if end:
        stmt = stmt.where(PriceBar.ts_utc <= end)
    rows = db.execute(stmt.order_by(PriceBar.ts_utc.desc()).limit(limit * 2)).all()
    rank = {k: i for i, k in enumerate(SOURCE_PRIORITY)}
    best: dict[object, tuple[PriceBar, Source]] = {}
    for b, s in rows:
        slot = b.ts_utc.date() if timeframe == "1d" else b.ts_utc
        if slot not in best or rank.get(s.key, 99) < rank.get(best[slot][1].key, 99):
            best[slot] = (b, s)
    return sorted(best.values(), key=lambda t: t[0].ts_utc)[-limit:]


def closed_only(rows: list[tuple[PriceBar, Source]], timeframe: str,
                now: datetime) -> list[tuple[PriceBar, Source]]:
    """Completed candles only: start + duration <= now. The running candle still changes."""
    delta = TIMEFRAME_DELTA[timeframe]
    return [(b, s) for b, s in rows if aware(b.ts_utc) + delta <= now]
