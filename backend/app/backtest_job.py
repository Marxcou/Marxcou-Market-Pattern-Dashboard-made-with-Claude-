"""Pattern backtest as a one-off job (not in the worker schedule because it runs 20 to 90 minutes,
depending on the machine).

Docker:   docker compose run --rm worker python -m app.backtest_job
Local:    cd backend && python -m app.backtest_job

Price source: the first configured daily data source from BACKTEST_SOURCES (Stooq with STOOQ_API_KEY,
otherwise Yahoo with YAHOO_ENABLED=true), or explicitly via --source. A run uses exactly one source, which is
named in the result (core rule 2). Without a configured source or without price data nothing is computed
or stored (core rule 6)."""
import argparse
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.adapters.base import PriceAdapter
from app.adapters.stooq import StooqAdapter
from app.adapters.yahoo import YahooAdapter
from app.analysis import fmt
from app.analysis.backtest import BacktestConfig, PatternSummary, share
from app.analysis.catalog import PATTERN_NAMES
from app.backtest_service import run_pattern_backtest
from app.backtest_universe import UNIVERSE_LABEL, default_universe, read_universe_file
from app.db import SessionLocal
from app.log_redaction import install as install_log_redaction

log = logging.getLogger("backtest")

# Sources with a long daily history for US and XETRA, tried in this order. Alpaca is deliberately missing:
# The free IEX feed only goes back a few years and does not cover XETRA.
BACKTEST_SOURCES: dict[str, tuple[type[PriceAdapter], str]] = {
    "stooq": (StooqAdapter, "STOOQ_API_KEY setzen"),
    "yahoo": (YahooAdapter, "YAHOO_ENABLED=true setzen"),
}
NO_SOURCE_TEXT = ("No daily data source configured ({hints} in .env). "
                  "No backtest is computed without real price data.")


def pick_source(wanted: str | None = None) -> PriceAdapter | str:
    """First configured source (or the requested one). Otherwise returns the reason as text."""
    keys = [wanted] if wanted else list(BACKTEST_SOURCES)
    for key in keys:
        cls, _ = BACKTEST_SOURCES[key]
        adapter = cls()
        if adapter.is_configured():
            return adapter
    return NO_SOURCE_TEXT.format(hints=" or ".join(BACKTEST_SOURCES[k][1] for k in keys))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    d = BacktestConfig()
    p = argparse.ArgumentParser(prog="python -m app.backtest_job", description="Pattern backtest with daily data")
    p.add_argument("--start", default="2010-01-01", help="first day of the price data (YYYY-MM-DD)")
    p.add_argument("--horizon", type=int, default=d.horizon_bars, help="candles after the starting point")
    p.add_argument("--min-move", type=float, default=d.min_move_pct, help="minimum move in %% for a hit")
    p.add_argument("--step", type=int, default=d.step_bars, help="distance between detection runs in candles")
    p.add_argument("--window", type=int, default=d.window_bars, help="candles per detection run")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1), help="parallel processes")
    p.add_argument("--symbols", help="only these symbols, e.g. SAP.XETR,AAPL.XNAS (for trying out)")
    p.add_argument("--universe-file", type=Path, help="custom list, one line per SYMBOL,EXCHANGE")
    p.add_argument("--cache-dir", type=Path, default=Path(os.environ.get("BACKTEST_CACHE_DIR", "backtest-cache")),
                   help="cache of the loaded daily data")
    p.add_argument("--max-cache-age-days", type=int, default=7)
    p.add_argument("--source", choices=list(BACKTEST_SOURCES),
                   help="force a price source (default: the first configured one from "
                        + ", ".join(BACKTEST_SOURCES) + ")")
    p.add_argument("--dry-run", action="store_true", help="only print, store nothing in the database")
    return p.parse_args(argv)


def _line(s: PatternSummary) -> str:
    name = PATTERN_NAMES[s.pattern_type]
    if s.hit_rate is None or s.ci_low is None or s.ci_high is None:
        return f"{name}: no evaluable cases"
    base = share(s.base_rate) if s.base_rate is not None else "not available"
    return (f"{name}: {share(s.hit_rate)} of {s.sample_size} cases (95%: {share(s.ci_low)} to "
            f"{share(s.ci_high)}), base rate {base}")


def main(argv: list[str] | None = None) -> int:
    install_log_redaction()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    a = parse_args(argv)
    cfg = BacktestConfig(horizon_bars=a.horizon, min_move_pct=a.min_move, window_bars=a.window, step_bars=a.step)
    adapter = pick_source(a.source)
    if isinstance(adapter, str):
        print(adapter, file=sys.stderr)
        return 2
    universe = read_universe_file(a.universe_file) if a.universe_file else default_universe()
    label = f"custom list ({len(universe)} symbols)" if a.universe_file else UNIVERSE_LABEL
    if a.symbols:
        wanted = {s.strip().upper() for s in a.symbols.split(",") if s.strip()}
        universe = [u for u in universe if f"{u[0]}.{u[1]}" in wanted]
        label = f"Selection ({len(universe)} symbols: {', '.join(sorted(wanted))})"
    start = datetime.fromisoformat(a.start).replace(tzinfo=UTC)
    log.info("Pattern backtest: %d symbols from %s, price source %s, %d processes", len(universe), fmt.day(start),
             adapter.metadata().name, a.workers)
    try:
        if a.dry_run:
            summaries, data = run_pattern_backtest(None, adapter, universe, label, start, cfg, a.workers,
                                                   a.cache_dir, timedelta(days=a.max_cache_age_days))
        else:
            with SessionLocal() as db:
                summaries, data = run_pattern_backtest(db, adapter, universe, label, start, cfg, a.workers,
                                                       a.cache_dir, timedelta(days=a.max_cache_age_days))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"\nPrice source: {adapter.metadata().name} ({adapter.metadata().homepage})")
    print(f"Evaluated: {len(data.series)} symbols, without data: {len(data.missing)}")
    for key, reason in sorted(data.missing.items()):
        print(f"  fehlt {key}: {reason}")
    for s in summaries:
        print(_line(s))
    print("\nNothing stored (--dry-run)." if a.dry_run else "\nResults stored (table backtest_runs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
