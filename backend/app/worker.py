"""Worker process: scheduler for retrievals and calculations. Phase 1A delivers only the skeleton:
the scheduler, the health-check job for all registered adapters and the hook point for further jobs."""
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler

from app.adapters.registry import load_builtin_adapters, news_adapters
from app.alpaca_stream import start_stream_thread
from app.analysis_service import analysis_job
from app.db import SessionLocal
from app.forecast_service import forecast_job
from app.log_redaction import install as install_log_redaction
from app.news_retention import retention_job
from app.news_service import make_job, sentiment_job
from app.pattern_service import pattern_job
from app.price_service import daily_job, intraday_job, quote_job
from app.sources_sync import sync_sources

log = logging.getLogger("worker")

# Workstreams 1B/2x/3x hook their jobs in here: (function, interval in seconds)
# 1B: price fallback by polling (the WebSocket delivers live), intraday candles, daily data
JOBS: list[tuple[Callable[[], None], int]] = [(quote_job, 60), (intraday_job, 120), (daily_job, 3600)]


def health_job() -> None:
    with SessionLocal() as db:
        sync_sources(db)


def build_scheduler() -> BlockingScheduler:
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(health_job, "interval", seconds=60, id="source-health", max_instances=1)
    for fn, seconds in JOBS:
        sched.add_job(fn, "interval", seconds=seconds, id=fn.__name__, max_instances=1)
    # Phase 2: one job per news source (own interval). Sources that are not enabled (no key,
    # feed not released) get no job and appear on the Sources page as 'disabled'.
    for adapter in news_adapters():
        if adapter.is_configured():
            key = adapter.metadata().key
            sched.add_job(make_job(key), "interval", seconds=adapter.poll_seconds, id=f"news-{key}",
                          max_instances=1, next_run_time=datetime.now(UTC) + timedelta(seconds=10))
    # Phase 3A: indicator events and price moves<->news (news also arrives later)
    sched.add_job(analysis_job, "interval", seconds=300, id="analysis", max_instances=1)
    # 3B: pattern detection (all patterns and zones, complete history, deterministic)
    sched.add_job(pattern_job, "interval", seconds=300, id="patterns", max_instances=1)
    # 4A: forecasts (daily candles) and forecast backtest; recomputes only when candles or patterns change
    sched.add_job(forecast_job, "interval", seconds=900, id="forecasts", max_instances=1,
                  next_run_time=datetime.now(UTC) + timedelta(minutes=2))
    sched.add_job(sentiment_job, "interval", seconds=300, id="sentiment", max_instances=1)
    sched.add_job(retention_job, "interval", seconds=86400, id="news-retention", max_instances=1,
                  next_run_time=datetime.now(UTC) + timedelta(minutes=5))
    return sched


def main() -> None:
    install_log_redaction()
    logging.basicConfig(level=logging.INFO)
    load_builtin_adapters()
    log.info("Worker gestartet")
    start_stream_thread()
    build_scheduler().start()


if __name__ == "__main__":
    main()
