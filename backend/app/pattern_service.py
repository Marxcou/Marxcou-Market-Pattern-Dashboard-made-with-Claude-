"""Run pattern detection for watchlist instruments and store the results (worker job).

Every run recomputes the complete history (deterministic). Detections are recognized by a fingerprint
(pattern type + start): status changes update the row, detections that are no longer found
(e.g. because a triangle turns out differently with a new turning point) are removed. Zones are replaced
on every run."""
import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import events as event_bus
from app.analysis import engine
from app.analysis.params import ALGO_VERSION, Params, default_params, params_hash
from app.analysis.patterns.common import Detection, Line
from app.analysis.series import Bars
from app.analysis.zones import Zone
from app.bars import aware, closed_only, load_bars
from app.db import SessionLocal
from app.models import (
    Instrument,
    PatternDetection,
    PatternScan,
    PriceBar,
    Source,
    SupportResistanceZone,
)
from app.price_service import watched_instruments

log = logging.getLogger("patterns")

TIMEFRAMES = ("1d", "1h")
BAR_LIMIT = 1500
FRESH_BARS = 2  # only changes to the latest candles trigger a live event
RECENT_BARS = 20  # "current" for /patterns/counts: forming or confirmed within the last 20 candles


def fingerprint(det: Detection, ts: list[datetime]) -> str:
    return hashlib.sha1(f"{det.pattern_type}|{ts[det.start_idx].isoformat()}".encode()).hexdigest()


def _line(line: Line, ts: list[datetime]) -> dict[str, Any]:
    return {"role": line.role, "label": line.label,
            "start": {"ts": ts[line.i0].isoformat(), "price": round(line.p0, 4)},
            "end": {"ts": ts[line.i1].isoformat(), "price": round(line.p1, 4)}, "extend_right": line.extend_right}


def _criteria(det: Detection | Zone) -> list[dict[str, Any]]:
    return [{"key": c.key, "name": c.name, "rule": c.rule, "threshold": c.threshold, "actual": c.actual,
             "unit": c.unit, "actual_text": c.actual_text, "required": c.required, "passed": c.passed,
             "sub_score": c.sub_score, "weight": c.weight} for c in det.criteria]


def _ts(ts: list[datetime], idx: int | None) -> datetime | None:
    return None if idx is None else ts[idx]


def bars_from_rows(rows: list[tuple[PriceBar, Source]]) -> Bars:
    return Bars.from_lists([aware(b.ts_utc) for b, _ in rows], [b.open for b, _ in rows], [b.high for b, _ in rows],
                           [b.low for b, _ in rows], [b.close for b, _ in rows], [b.volume for b, _ in rows])


def _sources(rows: list[tuple[PriceBar, Source]], start: int, end: int) -> tuple[list[int], datetime, bool]:
    used = rows[start : end + 1]
    return (sorted({s.id for _, s in used}), max(aware(b.fetched_at) for b, _ in used),
            any(b.is_demo for b, _ in used))


def scan_instrument(db: Session, inst: Instrument, timeframe: str, now: datetime | None = None,
                    params: Params | None = None, skip_unchanged: bool = False) -> dict[str, int]:
    """skip_unchanged: the worker job does not recompute if candles (count, last candle), parameters and
    algorithm version match the last run. Detection is deterministic, the result would be the same."""
    now = now or datetime.now(UTC)
    params = params or default_params()
    phash = params_hash(params)
    rows = closed_only(load_bars(db, inst.id, timeframe, limit=BAR_LIMIT), timeframe, now)
    scan = db.get(PatternScan, (inst.id, timeframe)) or PatternScan(instrument_id=inst.id, timeframe=timeframe)
    if (skip_unchanged and rows and scan.computed_at is not None and scan.params_hash == phash
            and scan.algo_version == ALGO_VERSION and scan.bar_count == len(rows)
            and scan.bars_to is not None and aware(scan.bars_to) == aware(rows[-1][0].ts_utc)):
        return {"new": 0, "updated": 0, "removed": 0, "zones": 0}
    scan.computed_at, scan.params_hash, scan.algo_version = now, phash, ALGO_VERSION
    scan.bar_count = len(rows)
    stats = {"new": 0, "updated": 0, "removed": 0, "zones": 0}
    if not rows:
        scan.empty_reason = "No price data stored yet."
        scan.bars_from = scan.bars_to = scan.recent_from = scan.last_fetched_at = None
        scan.source_ids = []
        db.add(scan)
        db.commit()
        return stats
    ts = [aware(b.ts_utc) for b, _ in rows]
    scan.bars_from, scan.bars_to = ts[0], ts[-1]
    scan.recent_from = ts[max(0, len(ts) - RECENT_BARS)]
    scan.source_ids = sorted({s.id for _, s in rows})
    scan.last_fetched_at = max(aware(b.fetched_at) for b, _ in rows)
    if len(rows) < engine.MIN_BARS:
        scan.empty_reason = (f"Too few candles for pattern detection (at least {engine.MIN_BARS}, "
                             f"available {len(rows)}).")
        db.add(scan)
        db.execute(delete(PatternDetection).where(PatternDetection.instrument_id == inst.id,
                                                  PatternDetection.timeframe == timeframe))
        db.execute(delete(SupportResistanceZone).where(SupportResistanceZone.instrument_id == inst.id,
                                                       SupportResistanceZone.timeframe == timeframe))
        db.commit()
        return stats
    scan.empty_reason = None
    db.add(scan)

    result = engine.detect(bars_from_rows(rows), timeframe, params)
    n = len(rows)
    existing = {d.fingerprint: d for d in db.scalars(select(PatternDetection).where(
        PatternDetection.instrument_id == inst.id, PatternDetection.timeframe == timeframe))}
    seen: set[str] = set()
    for det in result.detections:
        fp = fingerprint(det, ts)
        seen.add(fp)
        last_idx = max(det.end_idx, det.status_idx or det.end_idx)
        ids, fetched, demo = _sources(rows, 0, last_idx)
        values: dict[str, Any] = dict(
            pattern_type=det.pattern_type, name=det.name, direction=det.direction,
            start_ts=ts[det.start_idx], end_ts=ts[det.end_idx], formed_ts=ts[det.formed_idx], status=det.status,
            status_reason=det.status_reason, status_changed_at=_ts(ts, det.status_idx),
            confirmed_at=_ts(ts, det.confirmed_idx), invalidated_at=_ts(ts, det.invalidated_idx),
            breakout_direction=det.breakout_direction,
            key_points=[{"role": k.role, "label": k.label, "ts": ts[k.idx].isoformat(), "price": round(k.price, 4)}
                        for k in det.key_points],
            lines=[_line(line, ts) for line in det.lines], criteria=_criteria(det), confidence=det.confidence,
            confidence_breakdown=det.breakdown, confirmation_level=det.confirmation_level,
            invalidation_level=det.invalidation_level,
            scenarios=[{"kind": s.kind, "title": s.title, "trigger_level": s.trigger_level,
                        "trigger_rule": s.trigger_rule, "description": s.description} for s in det.scenarios],
            explanation=det.explanation, params=_params_for(det, params), params_hash=phash,
            algo_version=ALGO_VERSION, source_id=rows[det.end_idx][1].id, source_ids=ids, fetched_at=fetched,
            is_demo=demo,
        )
        row = existing.get(fp)
        previous = row.status if row else None
        if row is None:
            row = PatternDetection(instrument_id=inst.id, timeframe=timeframe, fingerprint=fp, detected_at=now,
                                   **values)
            db.add(row)
            stats["new"] += 1
        else:
            changed = any(getattr(row, k) != v for k, v in values.items() if not isinstance(v, datetime))
            for k, v in values.items():
                setattr(row, k, v)
            if changed:
                row.updated_at = now
                stats["updated"] += 1
        db.flush()
        fresh = max(det.formed_idx, det.status_idx or 0) >= n - FRESH_BARS
        if fresh and previous != det.status:
            event_bus.publish(db, "detection", {
                "category": "pattern", "detection_id": row.id, "instrument_id": inst.id, "symbol": inst.symbol,
                "timeframe": timeframe, "pattern_type": det.pattern_type, "name": det.name, "status": det.status,
                "previous_status": previous, "end_ts": ts[det.end_idx].isoformat()})
    stale = [fp for fp in existing if fp not in seen]
    if stale:
        db.execute(delete(PatternDetection).where(PatternDetection.instrument_id == inst.id,
                                                  PatternDetection.timeframe == timeframe,
                                                  PatternDetection.fingerprint.in_(stale)))
        stats["removed"] = len(stale)

    db.execute(delete(SupportResistanceZone).where(SupportResistanceZone.instrument_id == inst.id,
                                                   SupportResistanceZone.timeframe == timeframe))
    for z in result.zones:
        first, last = z.touches[0].idx, z.touches[-1].idx
        ids, fetched, demo = _sources(rows, first, n - 1)
        db.add(SupportResistanceZone(
            instrument_id=inst.id, timeframe=timeframe, kind=z.kind, lower=z.lower, upper=z.upper,
            touches=[{"ts": ts[q.idx].isoformat(), "price": round(q.price, 4),
                      "role": "hoch" if q.kind == "H" else "tief"} for q in z.touches],
            first_touch=ts[first], last_touch=ts[last], criteria=_criteria(z), confidence=z.confidence,
            confidence_breakdown=z.breakdown, explanation=z.explanation, params_hash=phash, algo_version=ALGO_VERSION,
            source_id=rows[n - 1][1].id, source_ids=ids, fetched_at=fetched, computed_at=now, is_demo=demo))
        stats["zones"] += 1
    db.commit()
    return stats


FAMILY_GROUPS: dict[str, list[str]] = {
    "doppelboden": ["pivots", "status", "doppel", "volumen"],
    "doppelhoch": ["pivots", "status", "doppel", "volumen"],
    "kopf_schulter": ["pivots", "status", "kopf_schulter", "volumen"],
    "kopf_schulter_invers": ["pivots", "status", "kopf_schulter", "volumen"],
    "dreieck_keil": ["pivots", "status", "dreieck_keil", "volumen"],
    "flagge_auf": ["flagge", "volumen", "pivots"],
    "flagge_ab": ["flagge", "volumen", "pivots"],
}


def _params_for(det: Detection, params: Params) -> dict[str, float]:
    return {f"{g}.{k}": v for g in FAMILY_GROUPS[det.family] for k, v in params[g].items()}


def pattern_job() -> None:
    """For all watchlist instruments (all users) and per timeframe; an error affects only that run."""
    with SessionLocal() as db:
        for inst in watched_instruments(db):
            for tf in TIMEFRAMES:
                try:
                    stats = scan_instrument(db, inst, tf, skip_unchanged=True)
                except Exception:  # noqa: BLE001 - one instrument must not stop the others
                    db.rollback()
                    log.exception("Mustererkennung %s/%s fehlgeschlagen", inst.symbol, tf)
                    continue
                if stats["new"] or stats["updated"] or stats["removed"]:
                    log.info("Muster %s/%s: %s", inst.symbol, tf, stats)
