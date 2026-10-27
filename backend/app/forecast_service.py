"""Compute and store forecasts and forecast backtests for watchlist instruments (worker job).

Completed daily candles only. There is one row per instrument and method in `forecasts` (replaced). The
backtest writes `backtest_runs` (kind='forecast', subject=method) and runs again when new candles are available and
the last run is older than BACKTEST_MAX_AGE. Error measures come only from stored candles; demo data
is marked as such (core rule 6)."""
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis import fmt
from app.analysis import forecast as fc
from app.bars import aware, closed_only, load_bars
from app.db import SessionLocal
from app.models import BacktestRun, Forecast, Instrument, PatternDetection
from app.price_service import watched_instruments

log = logging.getLogger("forecasts")

TIMEFRAME = "1d"
BAR_LIMIT = 2500
BACKTEST_MAX_AGE = timedelta(hours=20)
METHODS = (fc.PRIMARY, fc.COMPARISON)
# Increase when new stored fields or texts are added (without an algorithm change) so existing rows are rebuilt.
OUTPUT_VERSION = 3

NO_BARS_REASON = "No price data stored yet."
NOT_RUN_REASON = "The forecast has not been calculated for this instrument yet."
METHOD_NOTE = (
    "Rolling origin: on past days the forecast used only the candles known up to then and was compared "
    "with the closing price that occurred later. The naive reference \"price stays the same\" has no "
    "range; a lower pinball loss only shows that the bands carry information about the range of fluctuation, "
    "not that the direction is predicted."
)


def too_few_reason(n: int) -> str:
    return f"Too few candles for a forecast (at least {fc.MIN_BARS}, available {n})."


def params_hash(method: str) -> str:
    blob = json.dumps({"v": fc.ALGO_VERSION, "p": fc.DEFAULT_PARAMS[method], "b": fc.BACKTEST_PARAMS},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:8]


def universe_text(inst: Instrument) -> str:
    return f"{inst.symbol} ({inst.exchange}), own history"


# --- Backtest -------------------------------------------------------------------------------------------------


def _pct_text(x: float) -> str:
    return fmt.pct(x * 100, 0)


def verdict_text(h: fc.HorizonResult) -> str:
    return verdict_from_values(h.sample_size, h.coverage.get(0.8), h.better_than_naive, h.mae_model, h.mae_naive,
                               h.dm_p_value)


def verdict_from_values(sample_size: int, cov80: float | None, better: bool | None, mae_model: float,
                        mae_naive: float, dm_p_value: float | None) -> str:
    """Also used to render stored runs in the current language from their numbers."""
    cov = (f" The 80% band contained the actual price in {_pct_text(cov80)} of cases."
           if cov80 is not None else "")
    if better is None:
        return (f"Too few check points ({sample_size}) for a comparison with the naive reference "
                f"\"price stays the same\".{cov}")
    errs = f"error {fmt.pct(mae_model)} instead of {fmt.pct(mae_naive)}"
    p = f", p = {fmt.num(dm_p_value, 2)}" if dm_p_value is not None else ""
    if better:
        return f"At the median more accurate than the naive reference \"price stays the same\" ({errs}{p}).{cov}"
    return (f"At the median not demonstrably more accurate than the naive reference \"price stays the same\" "
            f"({errs}{p}).{cov}")


METRIC_NAMES = {"median_abs_error": "Mean absolute error of the median",
                "pinball_loss": "Pinball loss (mean over all quantiles)"}


def _horizon_json(h: fc.HorizonResult) -> dict[str, Any]:
    return {
        "horizon_bars": h.horizon_bars, "sample_size": h.sample_size,
        "coverage": [{"nominal": lvl, "observed": round(v, 4)} for lvl, v in sorted(h.coverage.items())],
        "metrics": [
            {"key": "median_abs_error", "name": METRIC_NAMES["median_abs_error"],
             "model": round(h.mae_model, 4), "naive": round(h.mae_naive, 4), "unit": "%"},
            {"key": "pinball_loss", "name": METRIC_NAMES["pinball_loss"],
             "model": round(h.pinball_model, 4), "naive": round(h.pinball_naive, 4), "unit": "%"},
        ],
        "skill": None if h.skill is None else round(h.skill, 4),
        "dm_p_value": None if h.dm_p_value is None else round(h.dm_p_value, 4),
        "better_than_naive": h.better_than_naive, "verdict_text": verdict_text(h),
    }


def run_backtest(db: Session, inst: Instrument, method: str, close: np.ndarray, ts: list[datetime],
                 source_ids: list[int], is_demo: bool, now: datetime) -> BacktestRun | None:
    seed_base = fc.seed_for(fc.ALGO_VERSION, "backtest", inst.symbol)
    res = fc.rolling_backtest(method, close, seed_fn=lambda o: seed_base + o)
    if res.sample_size == 0:
        return None
    main = res.at(fc.HORIZON)
    assert main is not None
    first, last = res.origins[0], res.origins[-1]
    run = BacktestRun(
        kind="forecast", subject=method, timeframe=TIMEFRAME, algo_version=fc.ALGO_VERSION,
        params={**res.params, "instrument_id": inst.id, "horizon_bars": fc.HORIZON,
                "data_until": ts[-1].isoformat(), "params_hash": params_hash(method)},
        universe=universe_text(inst),
        date_range=f"{ts[first].date().isoformat()} – {ts[last].date().isoformat()}",
        sample_size=res.sample_size, hit_rate=None, ci_low=None, ci_high=None, base_rate=None,
        metrics={"primary_horizon": fc.HORIZON, "by_horizon": [_horizon_json(h) for h in res.horizons],
                 "verdict_text": verdict_text(main), "method_note": METHOD_NOTE, "is_demo": is_demo,
                 "source_ids": source_ids},
        code_version=fc.ALGO_VERSION, created_at=now)
    db.add(run)
    db.flush()
    return run


def latest_backtest(db: Session, inst: Instrument, method: str) -> BacktestRun | None:
    runs = db.scalars(select(BacktestRun).where(
        BacktestRun.kind == "forecast", BacktestRun.subject == method, BacktestRun.timeframe == TIMEFRAME,
        BacktestRun.algo_version == fc.ALGO_VERSION, BacktestRun.universe == universe_text(inst))
        .order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc()))
    for r in runs:
        if (r.params or {}).get("instrument_id") == inst.id and (r.params or {}).get("params_hash") == \
                params_hash(method):
            return r
    return None


def _needs_backtest(run: BacktestRun | None, data_until: datetime, now: datetime) -> bool:
    if run is None:
        return True
    if run.params.get("data_until") == data_until.isoformat():
        return False
    return now - aware(run.created_at) >= BACKTEST_MAX_AGE


# --- Pattern levels ---------------------------------------------------------------------------------------------


def pattern_levels(db: Session, inst_id: int, paths: np.ndarray) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    dets = db.scalars(select(PatternDetection).where(
        PatternDetection.instrument_id == inst_id, PatternDetection.timeframe == TIMEFRAME,
        PatternDetection.status == "in_bildung").order_by(PatternDetection.id))
    for d in dets:
        levels = [s["trigger_level"] for s in d.scenarios if s.get("trigger_level") is not None]
        if len(levels) < 2 or max(levels) <= min(levels):
            continue
        upper, lower = float(max(levels)), float(min(levels))
        fp = fc.first_passage(paths, upper, lower)
        out.append({"detection_id": d.id, "fingerprint": d.fingerprint, "upper": upper, "lower": lower,
                    "p_upper": round(fp.upper_first, 4), "p_lower": round(fp.lower_first, 4),
                    "p_neither": round(fp.neither, 4), "horizon_bars": paths.shape[1]})
    return out


def _detections_signature(db: Session, inst_id: int) -> str:
    rows = db.execute(select(PatternDetection.id, PatternDetection.scenarios).where(
        PatternDetection.instrument_id == inst_id, PatternDetection.timeframe == TIMEFRAME,
        PatternDetection.status == "in_bildung").order_by(PatternDetection.id)).all()
    return json.dumps([[i, [s.get("trigger_level") for s in sc]] for i, sc in rows])


# --- Forecast ---------------------------------------------------------------------------------------------------


def _row(db: Session, inst_id: int, method: str) -> Forecast:
    row = db.scalar(select(Forecast).where(Forecast.instrument_id == inst_id, Forecast.timeframe == TIMEFRAME,
                                           Forecast.method == method))
    if row is None:
        row = Forecast(instrument_id=inst_id, timeframe=TIMEFRAME, method=method, params_hash=params_hash(method),
                       algo_version=fc.ALGO_VERSION)
        db.add(row)
    return row


def _set_empty(row: Forecast, reason: str, n: int, now: datetime) -> None:
    row.steps, row.pattern_levels, row.example_paths, row.horizon = [], [], [], 0
    row.based_on_until = row.last_close = row.bars_from = row.fetched_at = None
    row.backtest_run_id, row.backtest_reason = None, None
    row.bar_count, row.source_ids, row.is_demo = n, [], False
    row.params, row.params_hash, row.algo_version = dict(fc.DEFAULT_PARAMS[row.method]), \
        params_hash(row.method), fc.ALGO_VERSION
    row.inputs_hash, row.empty_reason, row.created_at = "", reason, now


def forecast_instrument(db: Session, inst: Instrument, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    rows = closed_only(load_bars(db, inst.id, TIMEFRAME, limit=BAR_LIMIT), TIMEFRAME, now)
    stats = {"forecasts": 0, "backtests": 0}
    n = len(rows)
    if n < fc.MIN_BARS:
        reason = NO_BARS_REASON if n == 0 else too_few_reason(n)
        for m in METHODS:
            _set_empty(_row(db, inst.id, m), reason, n, now)
        db.commit()
        return stats
    ts = [aware(b.ts_utc) for b, _ in rows]
    close = np.asarray([b.close for b, _ in rows], dtype=np.float64)
    source_ids = sorted({s.id for _, s in rows})
    fetched = max(aware(b.fetched_at) for b, _ in rows)
    is_demo = any(b.is_demo for b, _ in rows)
    future = fc.future_weekdays(ts[-1], fc.HORIZON)
    seed = fc.seed_for(fc.ALGO_VERSION, inst.symbol, ts[-1].isoformat(), f"{close[-1]:.6f}", n)
    signature = _detections_signature(db, inst.id)
    for m in METHODS:
        row = _row(db, inst.id, m)
        run = latest_backtest(db, inst, m)
        rerun = _needs_backtest(run, ts[-1], now)
        if rerun:
            new = run_backtest(db, inst, m, close, ts, source_ids, is_demo, now)
            if new is not None:
                run = new
                stats["backtests"] += 1
        inputs = hashlib.sha256(json.dumps([ts[-1].isoformat(), float(close[-1]), n, params_hash(m),
                                            signature, run.id if run else None, OUTPUT_VERSION]).encode()).hexdigest()
        if row.inputs_hash == inputs and row.empty_reason is None:
            continue
        f = fc.forecast(m, close, fc.HORIZON, seed=seed)
        row.horizon, row.based_on_until, row.last_close = fc.HORIZON, ts[-1], float(close[-1])
        row.steps = fc.quantile_rows(f.quantiles, future)
        row.params, row.params_hash, row.algo_version = f.params, params_hash(m), fc.ALGO_VERSION
        row.inputs_hash = inputs
        row.backtest_run_id = run.id if run else None
        row.backtest_reason = None if run else (
            "Too few candles for a backtest (at least "
            f"{fc.BACKTEST_PARAMS['min_train_bars'] + max(fc.BACKTEST_PARAMS['horizons'])}, available {n}).")
        row.pattern_levels = pattern_levels(db, inst.id, f.paths) if f.paths is not None else []
        row.example_paths = fc.example_path_rows(f.paths, future) if f.paths is not None else []
        row.bars_from, row.bar_count, row.source_ids, row.fetched_at = ts[0], n, source_ids, fetched
        row.empty_reason, row.is_demo, row.created_at = None, is_demo, now
        stats["forecasts"] += 1
    db.commit()
    return stats


def forecast_job() -> None:
    """For all watchlist instruments (all users); an error affects only that instrument."""
    with SessionLocal() as db:
        for inst in watched_instruments(db):
            try:
                stats = forecast_instrument(db, inst)
            except Exception:  # noqa: BLE001 - one instrument must not stop the others
                db.rollback()
                log.exception("Prognose %s fehlgeschlagen", inst.symbol)
                continue
            if stats["forecasts"] or stats["backtests"]:
                log.info("Prognose %s: %s", inst.symbol, stats)
