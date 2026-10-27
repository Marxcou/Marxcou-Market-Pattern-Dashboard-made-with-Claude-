"""Storing price data and the worker jobs. Every row gets source_id and fetched_at (core rule 2);
if a source is missing, nothing is invented and the job skips it."""
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.adapters.base import (
    BarRecord,
    InstrumentRecord,
    PriceAdapter,
    QuoteRecord,
    Timeframe,
)
from app.adapters.http import SourceError
from app.adapters.registry import price_adapters
from app.db import SessionLocal
from app.events import publish
from app.market_hours import session_active
from app.models import Instrument, PriceBar, Quote, Source, WatchlistItem
from app.sources_sync import sync_sources

log = logging.getLogger("price")

INTRADAY_LOOKBACK = {"1m": timedelta(days=5), "5m": timedelta(days=30), "1h": timedelta(days=180)}
DAILY_LOOKBACK = timedelta(days=365 * 5 + 2)
# Order when several sources provide the same candle: first configured source wins
SOURCE_PRIORITY = ["alpaca", "stooq", "yahoo"]
NO_INTRADAY_REASON = (
    "No intraday data for XETRA in the free tier. Daily data (end of trading) is available."
)


def ensure_source(db: Session, adapter: PriceAdapter) -> Source:
    meta = adapter.metadata()
    src = db.scalar(select(Source).where(Source.key == meta.key))
    if src is None:
        sync_sources(db)  # creates all registered sources with metadata
        src = db.scalar(select(Source).where(Source.key == meta.key))
    assert src is not None, f"Adapter {meta.key} is not registered"
    return src


def _source_id(db: Session, key: str) -> int:
    sid = db.scalar(select(Source.id).where(Source.key == key))
    if sid is None:
        raise SourceError(f"Unknown source {key}")
    return sid


def upsert_instrument(db: Session, rec: InstrumentRecord) -> Instrument:
    inst = db.scalar(select(Instrument).where(Instrument.symbol == rec.symbol, Instrument.exchange == rec.exchange))
    if inst is None:
        inst = Instrument(symbol=rec.symbol, exchange=rec.exchange, name=rec.name, currency=rec.currency,
                          isin=rec.isin, figi=rec.figi, provider_symbols={}, source_id=_source_id(db, rec.source_key),
                          fetched_at=rec.fetched_at)
        db.add(inst)
    else:
        inst.isin = inst.isin or rec.isin
        inst.figi = inst.figi or rec.figi
    db.commit()
    return inst


def store_bars(db: Session, instrument_id: int, bars: Sequence[BarRecord]) -> int:
    if not bars:
        return 0
    ids: dict[str, int] = {}
    rows = []
    for b in bars:
        sid = ids.setdefault(b.source_key, _source_id(db, b.source_key))
        rows.append(dict(instrument_id=instrument_id, timeframe=b.timeframe, ts_utc=b.ts_utc, source_id=sid,
                         open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume,
                         fetched_at=b.fetched_at, is_demo=False))
    stmt = sqlite_insert(PriceBar).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["instrument_id", "timeframe", "ts_utc", "source_id"],
        set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close", "volume", "fetched_at")},
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def store_quote(db: Session, instrument: Instrument, q: QuoteRecord) -> Quote:
    row = Quote(instrument_id=instrument.id, price=q.price, change_abs=q.change_abs, change_pct=q.change_pct,
                ts_utc=q.ts_utc, source_id=_source_id(db, q.source_key), fetched_at=q.fetched_at,
                delay_seconds=q.delay_seconds, is_demo=False)
    db.add(row)
    db.commit()
    publish(db, "quote", {
        "instrument_id": instrument.id, "symbol": instrument.symbol, "price": q.price,
        "change_abs": q.change_abs, "change_pct": q.change_pct, "ts_utc": q.ts_utc.isoformat(),
        "fetched_at": q.fetched_at.isoformat(), "source_key": q.source_key, "delay_seconds": q.delay_seconds,
    })
    prune_quotes(db, instrument.id)
    return row


def prune_quotes(db: Session, instrument_id: int, keep: int = 500) -> None:
    """Live ticks would otherwise fill the table without limit; the history lives in price_bars."""
    cutoff = db.scalar(select(Quote.id).where(Quote.instrument_id == instrument_id)
                       .order_by(Quote.id.desc()).offset(keep).limit(1))
    if cutoff is not None:
        db.query(Quote).filter(Quote.instrument_id == instrument_id, Quote.id <= cutoff).delete()
        db.commit()


def adapters_for(exchange: str, *, configured_only: bool = True) -> list[PriceAdapter]:
    found = [a for a in price_adapters() if exchange in a.supported_exchanges
             and (a.is_configured() or not configured_only) and a.metadata().kind == "price"]
    order = {k: i for i, k in enumerate(SOURCE_PRIORITY)}
    return sorted(found, key=lambda a: order.get(a.metadata().key, 99))


def has_intraday(exchange: str) -> bool:
    return exchange in ("XNYS", "XNAS")


def watched_instruments(db: Session) -> list[Instrument]:
    return list(db.scalars(select(Instrument).where(
        Instrument.id.in_(select(WatchlistItem.instrument_id).distinct()))))


def _latest_ts(db: Session, instrument_id: int, tf: str) -> datetime | None:
    ts = db.scalar(select(func.max(PriceBar.ts_utc)).where(PriceBar.instrument_id == instrument_id,
                                                          PriceBar.timeframe == tf))
    return ts.replace(tzinfo=UTC) if ts is not None and ts.tzinfo is None else ts


def backfill_instrument(db: Session, inst: Instrument, timeframes: Sequence[Timeframe]) -> int:
    """Fetches missing candles per timeframe. The first configured source with data wins."""
    total = 0
    now = datetime.now(UTC)
    for tf in timeframes:
        if tf != "1d" and not has_intraday(inst.exchange):
            continue
        lookback = DAILY_LOOKBACK if tf == "1d" else INTRADAY_LOOKBACK[tf]
        latest = _latest_ts(db, inst.id, tf)
        start = (latest - timedelta(days=3 if tf == "1d" else 1)) if latest else now - lookback
        for adapter in adapters_for(inst.exchange):
            try:
                bars = adapter.fetch_bars(inst.symbol, inst.exchange, tf, start, now)
            except SourceError as exc:
                log.warning("%s %s %s: %s", adapter.metadata().key, inst.symbol, tf, exc)
                continue
            if bars:
                total += store_bars(db, inst.id, bars)
                break
    return total


def refresh_quote(db: Session, inst: Instrument) -> bool:
    """Live adapters in order; for XETRA (daily data only) daily_job derives the price from the daily candles."""
    if not has_intraday(inst.exchange):
        return False
    for adapter in adapters_for(inst.exchange):
        try:
            q = adapter.fetch_quote(inst.symbol, inst.exchange)
        except SourceError as exc:
            log.warning("%s price %s: %s", adapter.metadata().key, inst.symbol, exc)
            continue
        if q:
            store_quote(db, inst, q)
            return True
    return False


def quote_from_daily(db: Session, inst: Instrument) -> bool:
    """Latest closing price from daily data, explicitly with source and delay 'end of trading'."""
    rows = db.execute(select(PriceBar).where(PriceBar.instrument_id == inst.id, PriceBar.timeframe == "1d")
                      .order_by(PriceBar.ts_utc.desc()).limit(2)).scalars().all()
    if not rows:
        return False
    last, prev = rows[0], rows[1] if len(rows) > 1 else None
    src = db.get(Source, last.source_id)
    assert src is not None
    ts = last.ts_utc if last.ts_utc.tzinfo else last.ts_utc.replace(tzinfo=UTC)
    # The candle of the current trading day changes until the end of trading (the source updates its closing price).
    # Only an unchanged value is skipped; otherwise the first retrieval of the day would stay all day.
    known = db.scalar(select(Quote.price).where(Quote.instrument_id == inst.id, Quote.ts_utc == ts,
                                               Quote.source_id == src.id).order_by(Quote.id.desc()).limit(1))
    if known is not None and known == last.close:
        return False
    store_quote(db, inst, QuoteRecord(
        symbol=inst.symbol, exchange=inst.exchange, price=last.close, ts_utc=ts, source_key=src.key,
        fetched_at=last.fetched_at, change_abs=last.close - prev.close if prev else None,
        change_pct=(last.close / prev.close - 1) * 100 if prev and prev.close else None, delay_seconds=None))
    return True


# --- Jobs (hooked in by the worker) ---

def quote_job() -> None:
    with SessionLocal() as db:
        for inst in watched_instruments(db):
            if not session_active(inst.exchange):
                continue
            try:
                refresh_quote(db, inst)
            except Exception:  # noqa: BLE001 - one instrument must not stop the others
                db.rollback()
                log.exception("Price %s failed", inst.symbol)


def intraday_job() -> None:
    with SessionLocal() as db:
        for inst in watched_instruments(db):
            if has_intraday(inst.exchange) and session_active(inst.exchange):
                try:
                    backfill_instrument(db, inst, ("1m", "5m", "1h"))
                except Exception:  # noqa: BLE001
                    db.rollback()
                    log.exception("Intraday candles %s failed", inst.symbol)


def daily_job() -> None:
    with SessionLocal() as db:
        for inst in watched_instruments(db):
            try:
                backfill_instrument(db, inst, ("1d",))
                if not has_intraday(inst.exchange):
                    quote_from_daily(db, inst)
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("Tageskerzen %s fehlgeschlagen", inst.symbol)


def backfill_new_instrument(instrument_id: int) -> None:
    """Right after adding to the watchlist, so the chart does not stay empty until the next job."""
    with SessionLocal() as db:
        inst = db.get(Instrument, instrument_id)
        if inst is None:
            return
        backfill_instrument(db, inst, ("1d", "1h", "5m", "1m"))
        if not refresh_quote(db, inst):
            quote_from_daily(db, inst)
