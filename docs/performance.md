# Measurements Phase 5A

Produced with `cd backend && python scripts/bench.py` (synthetic data in a temporary SQLite file, for measuring only).
Environment: cloud container, one process, 40 instruments (35 on the watchlists of 5 users), 20,000 news items,
200,000 entries in `events`. The numbers are orders of magnitude, not a promise for other machines.

## Worker jobs (run every 5 to 15 minutes)

| Job | Run with new data | Run without new candles, before | after |
|---|---|---|---|
| Pattern detection | 12.5 s | 12.5 s | 1.8 s |
| Analyses (events, moves) | 18.4 s | 9.1 s | 2.2 s |
| Forecasts | 13.6 s | 1.1 s (already had a hash comparison) | 1.1 s |

The remaining roughly 2 s per job is loading the candles (`load_bars`). A further lever would be a cheap
pre-check in SQL; at this size it is not worth it.

## API (median of 5 calls, one user)

All measured endpoints respond in under 100 ms (1m candles with 2,000 values 83 ms, indicators with five
indicators 58 ms, patterns 49 ms, watchlist with 15 instruments 14 ms, news list 9 ms). The query plans
of the main queries (news list, counters, candles, events) use existing indexes; no index is missing.

## Frontend bundle

`npm run build`: 450 kB JavaScript (141 kB gzip), 12.6 kB CSS. No action needed.

## Done

- The pattern and analysis jobs skip unchanged candles.
- The price and intraday jobs pause per instrument outside the trading hours of its exchange (`app/market_hours.py`, US in New York, XETRA in Berlin).
- `events` is trimmed to 24 hours (about 50,000 rows per day with 35 instruments). Only `/ws` reads the table (`app/main.py`); all displayed values come from `quotes`, `price_bars`, `news_*`, `pattern_*`, `indicator_events`, `backtest_runs`, `forecasts`.
- Error isolation per instrument in the price, intraday and daily candle jobs.

## Deliberately not changed

- Rate limits and circuit breakers per adapter already existed (`app/adapters/http.py`); the limits are below
  the limits of the free tiers (Alpaca 150/min, Finnhub 50/min, Yahoo 30/min).
- WebSocket: every open connection queries `events` by primary key once per second; for a circle of friends
  that is enough.
