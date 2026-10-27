"""Compute and store indicator events and notable price moves (worker job), including linking them in time
with news. All idempotent: events that are already stored are not created twice."""
import logging
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import events as event_bus
from app.analysis import events as ev
from app.analysis import moves as mv
from app.bars import aware, closed_only, load_bars
from app.db import SessionLocal
from app.models import (
    IndicatorEvent,
    Instrument,
    MoveNewsLink,
    NewsCluster,
    NewsInstrument,
    NotableMove,
    PriceBar,
    Source,
)
from app.price_service import watched_instruments

log = logging.getLogger("analysis")

TIMEFRAMES = ("1d", "1h")
BAR_LIMIT = 1500  # 1d: about 6 years; 1h: about 8 months of exchange time
LINK_MAX_AGE = timedelta(days=30)  # news can be back-filled; older moves are not linked again
FRESH_BARS = 2  # only events of the latest candles trigger a live event (WebSocket), no backfill storm


def build_series(rows: list[tuple[PriceBar, Source]], timeframe: str, currency: str) -> ev.Series:
    return ev.Series(
        ts=[aware(b.ts_utc) for b, _ in rows],
        open=np.array([b.open for b, _ in rows], dtype=float), high=np.array([b.high for b, _ in rows], dtype=float),
        low=np.array([b.low for b, _ in rows], dtype=float), close=np.array([b.close for b, _ in rows], dtype=float),
        volume=np.array([np.nan if b.volume is None else b.volume for b, _ in rows], dtype=float),
        timeframe=timeframe, currency=currency,
    )


def _source_info(rows: list[tuple[PriceBar, Source]], indices: list[int]) -> tuple[list[int], datetime]:
    used = [rows[i] for i in range(min(indices), max(indices) + 1)] if indices else rows
    ids = sorted({s.id for _, s in used})
    return ids, max(aware(b.fetched_at) for b, _ in used)


# Last evaluated state per (instrument, timeframe): (candle count, last candle). Worker process only;
# after a restart everything is computed once in full (idempotent, see below).
_last_seen: dict[tuple[int, str], tuple[int, datetime]] = {}


def analyze_instrument(db: Session, inst: Instrument, timeframe: str, now: datetime | None = None,
                       skip_unchanged: bool = False) -> dict[str, int]:
    """skip_unchanged (worker job): recompute events and moves only if there are new candles.
    Linking with news always runs because news can arrive after the move."""
    now = now or datetime.now(UTC)
    rows = closed_only(load_bars(db, inst.id, timeframe, limit=BAR_LIMIT), timeframe, now)
    stats = {"events": 0, "moves": 0, "links": 0}
    if len(rows) < 30:
        return stats
    state = (len(rows), aware(rows[-1][0].ts_utc))
    if skip_unchanged and _last_seen.get((inst.id, timeframe)) == state:
        recent = db.scalars(select(NotableMove).where(
            NotableMove.instrument_id == inst.id, NotableMove.timeframe == timeframe,
            NotableMove.algo_version == mv.ALGO_VERSION, NotableMove.move_start >= now - LINK_MAX_AGE)).all()
        stats["links"] = link_news(db, inst, timeframe, list(recent))
        return stats
    s = build_series(rows, timeframe, inst.currency)
    step = mv.TIMEFRAME_DELTA[timeframe]
    n = len(rows)

    existing = {(e.type, e.direction, aware(e.ts_utc)) for e in db.scalars(
        select(IndicatorEvent).where(IndicatorEvent.instrument_id == inst.id, IndicatorEvent.timeframe == timeframe,
                                     IndicatorEvent.algo_version == ev.ALGO_VERSION))}
    for e in ev.detect_all(s):
        key = (e.type, e.direction or "none", e.ts)
        if key in existing:
            continue
        # All loaded candles up to the marker enter the calculation (indicator lead-in), so their sources count.
        ids, fetched = _source_info(rows, [0, e.index])
        row = IndicatorEvent(
            instrument_id=inst.id, timeframe=timeframe, type=e.type, direction=e.direction or "none", ts_utc=e.ts,
            start_ts=s.ts[e.start_index], end_ts=s.ts[e.index], confirmed_at=s.ts[e.confirmed_index],
            title=e.title, summary=e.summary, criteria=e.criteria, values=e.values, params=e.params,
            algo_version=ev.ALGO_VERSION, source_id=rows[e.index][1].id, source_ids=ids, fetched_at=fetched,
            is_demo=any(b.is_demo for b, _ in rows[e.start_index:e.index + 1]))
        db.add(row)
        db.flush()
        stats["events"] += 1
        if e.confirmed_index >= n - FRESH_BARS:
            event_bus.publish(db, "detection", {
                "category": "indicator_event", "event_id": row.id, "instrument_id": inst.id, "timeframe": timeframe,
                "type": e.type, "direction": e.direction, "ts": e.ts.isoformat()})
    db.commit()

    known = {aware(m.move_start): m for m in db.scalars(select(NotableMove).where(
        NotableMove.instrument_id == inst.id, NotableMove.timeframe == timeframe,
        NotableMove.algo_version == mv.ALGO_VERSION))}
    params = mv.params_for(timeframe)
    for m in mv.detect_moves(s):
        start = s.ts[m.index]
        if start in known:
            continue
        ids, fetched = _source_info(rows, [max(0, m.index - params["lookback_bars"]), m.index])
        move = NotableMove(
            instrument_id=inst.id, timeframe=timeframe, move_start=start, move_end=start + step,
            return_pct=m.return_pct, return_z=m.return_z, volume_z=m.volume_z, reasons=m.reasons, params=params,
            algo_version=mv.ALGO_VERSION, source_id=rows[m.index][1].id, source_ids=ids, fetched_at=fetched,
            is_demo=rows[m.index][0].is_demo)
        db.add(move)
        known[start] = move
        stats["moves"] += 1
    db.commit()
    stats["links"] = link_news(db, inst, timeframe, [m for st, m in known.items() if st >= now - LINK_MAX_AGE])
    _last_seen[(inst.id, timeframe)] = state
    return stats


def link_news(db: Session, inst: Instrument, timeframe: str, moves: list[NotableMove]) -> int:
    """News clusters of the instrument whose first publication lies in the time window. Adds only missing
    links (news can arrive after the move)."""
    if not moves:
        return 0
    before, after = mv.WINDOWS[timeframe]
    added = 0
    for move in moves:
        start, end = aware(move.move_start), aware(move.move_end)
        rows = db.execute(
            select(NewsCluster, NewsInstrument.source_id)
            .join(NewsInstrument, NewsInstrument.cluster_id == NewsCluster.id)
            .where(NewsInstrument.instrument_id == inst.id,
                   NewsCluster.first_published_at >= start - timedelta(minutes=before),
                   NewsCluster.first_published_at <= end + timedelta(minutes=after))).all()
        have = set(db.scalars(select(MoveNewsLink.cluster_id).where(MoveNewsLink.move_id == move.id)))
        for cluster, source_id in rows:
            if cluster.id in have:
                continue
            offset = round((aware(cluster.first_published_at) - start).total_seconds() / 60)
            db.add(MoveNewsLink(move_id=move.id, cluster_id=cluster.id, time_offset_minutes=offset,
                                source_id=source_id))
            added += 1
    db.commit()
    return added


def analysis_job() -> None:
    """For all watchlist instruments (all users) and per timeframe; an error affects only that run."""
    with SessionLocal() as db:
        for inst in watched_instruments(db):
            for tf in TIMEFRAMES:
                try:
                    stats = analyze_instrument(db, inst, tf, skip_unchanged=True)
                except Exception:  # noqa: BLE001 - one instrument must not stop the others
                    db.rollback()
                    log.exception("Analyse %s/%s fehlgeschlagen", inst.symbol, tf)
                    continue
                if any(stats.values()):
                    log.info("Analyse %s/%s: %s", inst.symbol, tf, stats)
