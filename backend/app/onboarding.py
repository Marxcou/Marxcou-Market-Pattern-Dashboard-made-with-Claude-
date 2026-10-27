"""Immediate first calculation for an instrument newly put on a watchlist.

The periodic jobs (patterns/analysis every 5 minutes, forecast every 15 minutes) would only pick up a new instrument
with a delay. This run calls the same services once: price retrieval, pattern detection, indicator events,
forecast. Each step is secured individually; if one fails, the empty state with a reason remains and the
periodic jobs catch up."""
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis_service import TIMEFRAMES as ANALYSIS_TIMEFRAMES
from app.analysis_service import analyze_instrument
from app.db import SessionLocal
from app.forecast_service import forecast_instrument
from app.models import Instrument, WatchlistItem
from app.pattern_service import TIMEFRAMES as PATTERN_TIMEFRAMES
from app.pattern_service import scan_instrument
from app.price_service import backfill_new_instrument, has_intraday

log = logging.getLogger("onboarding")

# For this long after adding, a missing result counts as "being calculated". After that the interface shows
# the plain empty state with a reason again, so a failed run does not appear as waiting forever.
PENDING_WINDOW = timedelta(minutes=15)


def is_pending(db: Session, instrument_id: int, now: datetime | None = None) -> bool:
    """True if the instrument landed on a watchlist within the time window (calculation running/pending)."""
    now = now or datetime.now(UTC)
    added = db.scalar(select(func.max(WatchlistItem.added_at)).where(WatchlistItem.instrument_id == instrument_id))
    if added is None:
        return False
    if added.tzinfo is None:
        added = added.replace(tzinfo=UTC)
    return now - added < PENDING_WINDOW


def _step(db: Session, label: str, fn: Callable[[], object]) -> None:
    try:
        fn()
    except Exception:  # noqa: BLE001 - one step must not prevent the following ones
        db.rollback()
        log.exception("Erstberechnung %s fehlgeschlagen", label)


def process_new_instrument(instrument_id: int) -> None:
    """Background task after adding to the watchlist."""
    with SessionLocal() as db:
        inst = db.get(Instrument, instrument_id)
        if inst is None:
            return
        _step(db, f"{inst.symbol} Kursabruf", lambda: backfill_new_instrument(instrument_id))
        for tf in PATTERN_TIMEFRAMES:
            if tf != "1d" and not has_intraday(inst.exchange):
                continue  # without intraday candles there is nothing to detect; the API gives the reason
            _step(db, f"{inst.symbol} Muster {tf}", partial(scan_instrument, db, inst, tf))
        for tf in ANALYSIS_TIMEFRAMES:
            if tf != "1d" and not has_intraday(inst.exchange):
                continue
            _step(db, f"{inst.symbol} Analyse {tf}", partial(analyze_instrument, db, inst, tf))
        _step(db, f"{inst.symbol} Prognose", lambda: forecast_instrument(db, inst))
