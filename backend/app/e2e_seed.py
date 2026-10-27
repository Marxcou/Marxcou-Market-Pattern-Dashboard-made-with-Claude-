"""Labeled test data for the end-to-end tests (Playwright) and local visual checks.

    DEMO_MODE=true python -m app.e2e_seed

Core rule 6: This data is invented and is never presented as real. The command only runs with DEMO_MODE=true
(banner "DEMO MODE" in the interface); candles and prices carry is_demo=true, instruments and sources are called
"Demo ..." or "(sample data)". The run is repeatable (existing demo rows stay, analyses are recomputed).
Patterns, indicator events and forecast are created with the same services as in operation; only the
pattern backtest is a hard-coded test run with a recognizable universe label."""
import logging
import sys
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.params import ALGO_VERSION
from app.analysis_service import TIMEFRAMES as ANALYSIS_TIMEFRAMES
from app.analysis_service import analyze_instrument
from app.bootstrap import ensure_admin
from app.config import get_settings
from app.db import SessionLocal
from app.forecast_service import forecast_instrument
from app.log_redaction import install as install_log_redaction
from app.models import (
    BacktestRun,
    Instrument,
    NewsCluster,
    NewsInstrument,
    NewsItem,
    PriceBar,
    Quote,
    Sentiment,
    Source,
)
from app.pattern_service import scan_instrument

log = logging.getLogger("e2e_seed")

BARS = 420
LABEL = "Beispieldaten"

# Price course: slow lead-in, then double bottom (lows at ~100 and ~100.3, neckline ~110). DEMOA: confirmed
# breakout (chart tests), DEMOB: still forming (counter on the watchlist).
ANCHORS: dict[str, list[tuple[int, float]]] = {
    "DEMOA": [(0, 140), (250, 120), (280, 100), (295, 110), (310, 100.3), (335, 118), (360, 125), (BARS - 1, 124)],
    # double bottom still forming (counts as a "currently detected pattern" on the watchlist card)
    "DEMOB": [(0, 140), (350, 120), (380, 100), (395, 110), (410, 100.3), (BARS - 1, 106)],
}
NAMES = {"DEMOA": "Demo Beispiel AG", "DEMOB": "Demo Muster Holding"}


def _series(anchors: list[tuple[int, float]], seed: int) -> np.ndarray:
    xs, ys = [a[0] for a in anchors], [a[1] for a in anchors]
    base = np.interp(np.arange(BARS), xs, ys)
    noise = np.random.default_rng(seed).normal(0, 0.002, BARS)
    noise[np.isin(np.arange(BARS), xs)] = 0.0  # Wendepunkte bleiben exakt
    return np.asarray(base * (1 + noise))


def _source(db: Session, key: str, name: str, kind: str, description: str, now: datetime) -> Source:
    row = db.scalar(select(Source).where(Source.key == key)) or Source(key=key)
    row.name, row.kind, row.description = name, kind, description
    row.homepage, row.terms_url = "https://example.org/demo", "https://example.org/demo/terms"
    row.update_interval, row.delay_text = "only when the test data is loaded", "none (invented sample data)"
    row.requires_key, row.is_official = False, False
    row.status, row.last_success_at, row.last_error = "online", now, None
    db.add(row)
    db.flush()
    return row


def _instrument(db: Session, symbol: str, exchange: str, currency: str, src: Source, now: datetime) -> Instrument:
    inst = db.scalar(select(Instrument).where(Instrument.symbol == symbol, Instrument.exchange == exchange))
    if inst is None:
        inst = Instrument(symbol=symbol, name=f"{NAMES[symbol]} ({LABEL})", exchange=exchange, currency=currency,
                          provider_symbols={}, source_id=src.id, fetched_at=now)
        db.add(inst)
        db.flush()
    return inst


def _bars_and_quote(db: Session, inst: Instrument, src: Source, seed: int, now: datetime) -> None:
    close = _series(ANCHORS[inst.symbol], seed)
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) * 1.004
    low = np.minimum(open_, close) * 0.996
    last_day = datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=1)
    have = {ts.replace(tzinfo=UTC) for ts in db.scalars(
        select(PriceBar.ts_utc).where(PriceBar.instrument_id == inst.id, PriceBar.timeframe == "1d"))}
    vol = np.random.default_rng(seed + 1).integers(800_000, 1_200_000, BARS)
    for i in range(BARS):
        ts = last_day - timedelta(days=BARS - 1 - i)
        if ts in have:
            continue
        db.add(PriceBar(instrument_id=inst.id, timeframe="1d", ts_utc=ts, source_id=src.id, open=float(open_[i]),
                        high=float(high[i]), low=float(low[i]), close=float(close[i]), volume=float(vol[i]),
                        fetched_at=now, is_demo=True))
    if db.scalar(select(Quote.id).where(Quote.instrument_id == inst.id).limit(1)) is None:
        prev = float(close[-2])
        db.add(Quote(instrument_id=inst.id, price=float(close[-1]), change_abs=float(close[-1] - prev),
                     change_pct=float((close[-1] / prev - 1) * 100), ts_utc=last_day, source_id=src.id,
                     fetched_at=now, delay_seconds=None, is_demo=True))


def _news(db: Session, inst: Instrument, sa: Source, sb: Source, sent: Source, now: datetime) -> None:
    if db.scalar(select(NewsCluster.id).limit(1)) is not None:
        return
    spec = [
        ("Demo Example Corp reports third-quarter figures (sample item)", 30, "positiv", 0.6,
         "Sample item with invented content for checking the interface.", ["third-quarter figures"]),
        ("Demo Example Corp announces board change (sample item)", 26 * 60, "neutral", 0.0,
         "Sample item with invented content for checking the interface.", []),
    ]
    for n, (title, minutes_ago, label, score, excerpt, evidence) in enumerate(spec):
        pub = now - timedelta(minutes=minutes_ago)
        cluster = NewsCluster(canonical_title=title, first_published_at=pub, last_published_at=pub, item_count=2)
        db.add(cluster)
        db.flush()
        for s, tag in ((sa, "a"), (sb, "b")):
            db.add(NewsItem(source_id=s.id, external_id=f"demo-{n}-{tag}", url=f"https://example.org/demo/{n}/{tag}",
                            url_normalized=f"example.org/demo/{n}/{tag}", title=title, excerpt=excerpt,
                            published_at=pub, fetched_at=now, language="en", publisher=s.name, cluster_id=cluster.id))
        db.add(NewsInstrument(cluster_id=cluster.id, instrument_id=inst.id, match_method="provider_tag",
                              source_id=sa.id, fetched_at=now))
        db.add(Sentiment(cluster_id=cluster.id, label=label, score=score, evidence=evidence,
                         rationale="Invented sample rationale for checking the interface.",
                         method="lexicon", model_name="Demo lexicon (sample data)", model_version="e2e",
                         source_id=sent.id))


def _pattern_backtest(db: Session) -> None:
    """Hard-coded test run so the explanation panel shows the backtest block. The universe names it as a demo."""
    if db.scalar(select(BacktestRun.id).where(BacktestRun.kind == "pattern", BacktestRun.subject == "doppelboden",
                                              BacktestRun.universe.like("Demo%"))) is not None:
        return
    db.add(BacktestRun(
        kind="pattern", subject="doppelboden", timeframe="1d", algo_version=ALGO_VERSION,
        params={"horizon_bars": 20, "min_move_pct": 3.0}, universe="Demo universe (invented sample data)",
        sample_size=120, hit_rate=0.6, ci_low=0.51, ci_high=0.69, base_rate=0.5, date_range="Sample period",
        metrics={"verdict_text": "Sample value for checking the interface, not a real hit rate.",
                 "survivorship_note": "Invented sample data.",
                 "scenarios": {"bestaetigung": {"share": 0.6, "sample_size": 120,
                                                "text": "Sample value, not real statistics."}}}))


def seed() -> None:
    if not get_settings().demo_mode:
        sys.exit("Aborted: The test data is invented and may only be created with DEMO_MODE=true "
                 "(core rule 6).")
    now = datetime.now(UTC)
    with SessionLocal() as db:
        ensure_admin(db)
        price = _source(db, "demo_kurse", "Demo price source (sample data)", "price",
                        "Invented candles for tests. No real market data.", now)
        na = _source(db, "demo_news_a", "Demo news source A (sample data)", "news",
                     "Invented items for tests.", now)
        nb = _source(db, "demo_news_b", "Demo news source B (sample data)", "news",
                     "Invented items for tests.", now)
        sent = _source(db, "demo_stimmung", "Demo sentiment method (sample data)", "reference",
                       "Invented sentiment values for tests.", now)
        insts = [_instrument(db, "DEMOA", "XETR", "EUR", price, now),
                 _instrument(db, "DEMOB", "XNAS", "USD", price, now)]
        for i, inst in enumerate(insts):
            _bars_and_quote(db, inst, price, 100 + i, now)
        _news(db, insts[0], na, nb, sent, now)
        _pattern_backtest(db)
        db.commit()
        for inst in insts:
            scan_instrument(db, inst, "1d", now=now)
            for tf in ANALYSIS_TIMEFRAMES:
                if tf == "1d":
                    analyze_instrument(db, inst, tf, now=now)
            forecast_instrument(db, inst, now=now)
        log.info("Testdaten angelegt: %s", ", ".join(i.symbol for i in insts))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    install_log_redaction()
    seed()
