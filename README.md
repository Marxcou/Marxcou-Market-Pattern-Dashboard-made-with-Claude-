# Market Pattern Dashboard (Marktmuster-Dashboard)

Information tool for stocks: news, charts, pattern detection, scenarios. **Not investment advice.** The core rules (Grundregeln) are in [CLAUDE.md](CLAUDE.md).

The interface is English by default and can be switched to German with the EN/DE switch in the header. The code uses a few German domain identifiers (for example pattern types such as `doppelboden` and status values such as `bestaetigt`); they are part of the API contract and are listed in `docs/api-contract.md`.

Status: **Phase 1A + 1B (foundation, price data backend), Phase 2 backend (news aggregator), and the phases after it as described below.** Login, user management, database, API, worker and the interface with disclaimer, dark mode and localized number and date formats are running. The backend fetches price data (see below).

## News (Phase 2, backend)

For each source the worker fetches items about the stocks on all watchlists at that source's own interval, assigns them to instruments (provider symbol, ISIN, ticker, company name; the reason is stored with every assignment), merges duplicates into clusters (normalized URL, title similarity within 48 hours, **all** sources of a cluster stay visible) and rates the sentiment with a rationale and the model used. Only the headline, an excerpt of at most 300 characters and the link are stored. Endpoints: `/api/news`, `/api/instruments/{id}/news`, `/api/news/counts`, `/api/news/sentiment-status`, `/api/sources` (see `docs/api-contract.md`).

| Source | Key in `.env` | Note |
|---|---|---|
| Finnhub company news | `FINNHUB_API_KEY` (same as for prices) | US only, every 5 min |
| SEC EDGAR | `SEC_EDGAR_CONTACT_EMAIL` | Mandatory filings (8-K, 10-Q, 10-K, Form 4); a contact address is required in the User-Agent |
| Marketaux | `MARKETAUX_API_KEY` | 100 requests/day: stocks are queried in rotation, at most 90 requests/day |
| Alpha Vantage News (optional) | `ALPHAVANTAGE_API_KEY` | 25 requests/day, at most 20 used |
| GDELT | none | noisy: items without a company name or ticker in the title are discarded |
| Investor relations feeds | `IR_FEEDS` | **off by default**: check the address and terms of use of each IR page first |
| RSS feeds, EQS | `RSS_ENABLED_FEEDS`, `EQS_RSS_URL` | **off by default**: check the address and terms of use first |

Sources without a key or without activation appear on the Sources page as "disabled" with the reason; the failure of one source does not affect the others.

**Sentiment:** A rule-based word list method (German/English, free of charge) is always available. With `ANTHROPIC_API_KEY`, Claude Haiku 4.5 rates the items and must quote the triggering phrases verbatim; the backend checks every quote against the text and falls back to the word list on any mismatch. `CLAUDE_MONTHLY_BUDGET_USD` (default 10) is a hard cap: before every call the month's spending plus the call's maximum cost is checked. After that the word list applies, visible in `/api/news/sentiment-status` and on the Sources page. Please also set a spending limit in the Anthropic console.

**Explanation texts "In plain words":** For every pattern detection and for the forecast, the dashboard shows a short text that summarizes the calculated values in plain language. With `ANTHROPIC_API_KEY`, Claude Sonnet 5.5 writes it solely from those values (criteria, confidence, scenarios, backtest, corridor); it is labeled "AI-generated" with model and time, and is generated and stored once per data state. The backend then checks every text: length, word list from `grundregeln.py`, no links, and every number and date must appear in the values. If the text fails the check, there is no key, the monthly limit is reached or the data is demo data, a deterministic template is shown instead, explicitly labeled "Template, no AI" with the reason. The cost counts against the same `CLAUDE_MONTHLY_BUDGET_USD` as sentiment (roughly 1 cent per text).

**Claude via the Batch API (default, `CLAUDE_USE_BATCH=true`):** New items appear immediately with the word-list sentiment; Claude is queried in parallel through the Batch API (half price) and replaces it as soon as the result arrives (usually minutes, at most 24 hours). The quote check is the same as for single calls. For open batches the maximum amount is reserved against the monthly limit. Answers that cannot be verified stay with the word list and are not requested again; expired requests are resubmitted. With `CLAUDE_USE_BATCH=false` the former single call applies.

**Daily quotas:** The counter for Marketaux and Alpha Vantage lives in the table `api_usage` and survives restarts (day changes at 00:00 UTC).

**Retention:** A daily job deletes clusters whose latest item is older than `NEWS_RETENTION_DAYS` (default 90, minimum 14, 0 = off), together with their items, assignments and sentiment.

## Indicators and events (Phase 3A, backend)

Every 5 minutes the worker evaluates all watchlist instruments (timeframes 1d and 1h, completed candles only):

- **Indicators for the chart** (`GET /api/instruments/{id}/indicators`): SMA, EMA, RSI (Wilder), MACD, Bollinger Bands, calculated on the fly from the stored candles. The formulas are in the response and in `backend/app/analysis/indicators.py`.
- **Indicator events** (`/indicator-events`): golden/death cross (SMA 50/200), RSI divergence, Bollinger breakout, volume spike. Every event states its criteria with actual values, parameters, algorithm version and the price sources. There is no historical hit rate for them yet (it comes with the backtest); the response says so explicitly.
- **Notable price moves and news** (`/move-links`): return or volume outliers (z-score ≥ 3 against the preceding 60 candles), assigned by time to items about the same instrument. Purely temporal, no statement about a cause.

Parameters are in `backend/app/analysis/events.py` (`PARAMS`) and `moves.py`; tests with synthetic series are in `backend/tests/test_indicator_events.py`. Contract: `docs/api-contract.md`.

## Pattern detection (Phase 3B, backend)

Every 5 minutes the worker searches all watchlist instruments (1d and 1h, completed candles only, up to 1,500 candles) for chart patterns using deterministic rules:

- **Patterns:** head and shoulders (also inverse), double top/double bottom, triangles (ascending, descending, symmetrical), wedges (rising, falling), flags and pennants (after a rise/decline). The basis is turning points found with a ZigZag with an ATR threshold (`backend/app/analysis/pivots.py`).
- **Support and resistance zones** from clusters of turning points (`backend/app/analysis/zones.py`).
- **Explanation per detection:** location (key points, lines, period), every criterion with its rule and actual value, confidence as the weighted mean of the sub-scores with a breakdown, scenarios "Confirmation"/"Failure" with price levels (not price forecasts), status (forming, confirmed, invalid) with a reason.
- **Historical hit rate:** comes from the pattern backtest (see below, table `backtest_runs`). As long as it has not run, the API returns `"status": "nicht_berechnet"` (not calculated) without numbers.

All parameters with descriptions are in `backend/app/analysis/params.py` and under `GET /api/patterns/catalog`; every detection stores the values used, `params_hash` and `algo_version`. Endpoints: `GET /api/instruments/{id}/patterns`, `/api/patterns/{id}`, `/api/patterns/counts`. Tests with synthetic price series with known results: `backend/tests/test_patterns.py`, `test_pattern_api.py`.

## Pattern backtest (Phase 3C)

The historical hit rate per pattern type is calculated with real daily data. The backtest is a one-off job (not part of the worker schedule) and uses the first configured daily data source: **Stooq** if `STOOQ_API_KEY` is set, otherwise **Yahoo Finance (unofficial)** if `YAHOO_ENABLED=true` is set. `--source stooq` or `--source yahoo` forces the source. A run uses exactly one source; it is stated in the result (`metrics.source`, text "Daily data from …") and in the pattern view next to the hit rate. If no source is configured or it returns nothing, the job calculates and stores nothing; until the first run the dashboard shows "not calculated".

Yahoo is unofficial: there is no documented API, retrieval can fail without notice, and its terms of use do not explicitly allow this use. Prices are split-adjusted, not dividend-adjusted.

```bash
# try two symbols first, without storing anything
docker compose run --rm worker python -m app.backtest_job --symbols SAP.XETR,AAPL.XNAS --dry-run
# full run (DAX selection and 100 US stocks since 2010), the result is stored in the database
docker compose run --rm worker python -m app.backtest_job
```

Without Docker: `cd backend && python -m app.backtest_job` (same options). The full run downloads about 140 daily series (Stooq: 20 requests per minute, so about 7 minutes; Yahoo: at most 30 per minute) and needs about 1 CPU minute per stock, spread over all cores but one (`--workers`). The downloaded data is cached for 7 days in `BACKTEST_CACHE_DIR`, so a second run does not query the source again (kept separately per source). Further options: `--source`, `--start`, `--horizon` (candles, default 20), `--min-move` (%, default 5), `--step`, `--window`, `--universe-file` (your own list, one `SYMBOL,EXCHANGE` per line), `python -m app.backtest_job --help`.

How it is calculated (`backend/app/analysis/backtest.py`):

- **No look-ahead:** Pattern detection runs step by step (every 5 candles) using only the candles up to the respective day (at most 500). A case is a confirmed pattern. The starting point is the closing price on the day of confirmation or, if the pattern only became visible later, on that later day.
- **Hit:** A closing price within 20 candles is at least 5 % in the direction of the pattern (for the symmetrical triangle, in the direction of the breakout).
- **Base rate:** the same test for every trading day of the same stocks in the same period, weighted like the cases. The 95 % interval of the hit rate comes from the Wilson formula. If its lower bound is not above the base rate, the dashboard shows "Historically not better than chance".
- **Scenarios:** For "Confirmation"/"Failure" (or "Breakout upward/downward") it counts how often patterns detected while forming later became confirmed or invalid.
- **Excluded:** periods with a daily jump above 40 % (for example unadjusted stock splits) and cases with fewer than 20 candles after them. Both are counted and stored.
- **Stated openly:** The stock selection consists of today's index members (survivorship bias). Cases of the same stock overlap in time, so the interval tends to be too narrow. The DAX list in `backend/app/backtest_universe.py` is to the best of our knowledge (as of 2025) and should be checked before the run.

Every run stores one row per pattern type in `backtest_runs` with parameters, period, source, fetch time, values used and missing values. The dashboard always shows the latest run. Tests with synthetic price series with known results: `backend/tests/test_backtest.py`.

## Forecasts and forecast quality (Phase 4A, backend)

Every 15 minutes the worker calculates a forecast corridor over 20 trading days for all watchlist instruments (completed daily candles only, from 250 candles), but only recalculates when candles, patterns or the backtest have changed:

- **Main method:** Monte Carlo simulation using a block bootstrap (4,000 paths made of blocks of 10 historical daily returns from the last 750 days, trend removed). The result is quantiles (2.5/10/25/50/75/90/97.5 %) per day, which gives the 50/80/95 % bands. The median (50 %) is delivered as the "median path" inside the corridor, plus five example paths from the simulation (end value at the 10th/30th/50th/70th/90th percentile); there is no line without a corridor.
- **Comparison:** ARIMA(1,1,0) on log prices (own numpy implementation, least squares, normally distributed errors).
- **Forecast backtest:** rolling origin on the instrument's own history (a test point every 5 days, up to 300), without look-ahead. It measures band coverage, mean absolute error of the median and pinball loss, each against the naive reference "price stays the same", for 5, 10 and 20 days. "Better than naive" only applies with a smaller error and a Diebold-Mariano test p < 0.05; otherwise it says openly "not demonstrably more accurate". Results are stored in `backtest_runs` (`kind = "forecast"`).
- **Pattern scenarios:** for patterns that are forming, the share of simulated paths that reach the confirmation or invalidation level first, next to the historical rate from the pattern backtest. The simulation does not know the pattern; the response says so.

Code: `backend/app/analysis/forecast.py` (pure numpy, deterministic seed per data state), `backend/app/forecast_service.py`, `backend/app/api/forecasts.py`. Endpoints: `GET /api/instruments/{id}/forecast`, `GET /api/forecasts/methods`. Tests: `backend/tests/test_forecast.py`, `test_forecast_api.py`.

## Forecast corridor in the frontend (Phase 4B)

On the chart page (daily candles) the **forecast corridor** can be switched on: three nested probability ranges (50, 80 and 95 %) behind the last candle, never a line without a corridor. Inside the corridor a dashed line shows the **median path** (median per day, switch "Median path", on by default); the panel also states how far the actual price was from this line on average in the backtest after 5, 10 and 20 days, next to the reference "price stays the same". With "Example paths" five individual simulated paths appear, pale and labeled as examples. Because the trend of the past is removed on purpose, the median usually runs close to the last closing price. Below it is the panel with the values at the end of the horizon (5, 10 or 20 candles), "How is this calculated?" (method, assumptions, limits, parameters), the **forecast quality** from the backtest (band coverage, error measures against the naive reference "price stays the same", sample, significance test) and the comparison method ARIMA. If a pattern is selected, its confirmation and invalidation levels appear as lines up to the end of the corridor, together with their position in the corridor, simulated path shares and the historical rate from the pattern backtest side by side. If the forecast or the backtest is missing, that is stated with the reason; if the method is not demonstrably better than the reference, that is stated too. Code: `frontend/src/components/ForecastPanel.tsx`, `frontend/src/lib/forecast.ts`, tests `frontend/src/forecast.test.tsx`; contract: `docs/api-contract.md`, section "Phase 4A".

## Price data (Phase 1B)

| Source | Scope | Key in `.env` |
|---|---|---|
| Alpaca (IEX) | US: live prices via WebSocket, candles 1m/5m/1h/1d | `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` |
| Finnhub | US: price as a fallback source | `FINNHUB_API_KEY` |
| Stooq | Daily data US and XETRA | `STOOQ_API_KEY` |
| Yahoo Finance (unofficial) | Daily data US and XETRA, if Stooq is missing | `YAHOO_ENABLED=true` (no key) |
| OpenFIGI | Search by ticker, name, ISIN | optional `OPENFIGI_API_KEY` |

The worker only fetches data for stocks that are on at least one watchlist. If a key is missing, `/api/sources` shows the status `disabled`; no substitute data is generated. XETRA only has daily data on the free tier: 1D/1W show an explicit notice for it. Prices from the Alpaca live feed come from the IEX exchange and may differ from the consolidated price. The failure of one source stays local (rate limit, retry, circuit breaker per adapter).

## Stability and speed (Phase 5A)

Measured with `backend/scripts/bench.py` (40 instruments, 35 of them on watchlists, 1,500 daily candles, several thousand candles per timeframe, 20,000 items; results in `docs/performance.md`):

- The worker jobs for patterns and analyses now only recalculate when there are new completed candles (or when parameters or the algorithm version change). A run without new candles therefore takes about 2 s instead of 12 s (patterns) or 9 s (analyses). Detection is deterministic, so the result would be identical.
- `quote_job` and `intraday_job` only query each instrument during the trading hours of its exchange (`backend/app/market_hours.py`, each with its own time zone): US Mon to Fri 04:00 to 20:30 New York, XETRA Mon to Fri 08:00 to 18:30 Berlin. Holidays are not modeled. Today only the US part fetches intraday data (XETRA only has daily data on the free tier, which would run hourly unchanged); the XETRA hours apply as soon as an intraday provider is added.
- The event queue (`events`) is trimmed to 24 hours in the daily cleanup job. Before that it grew without limit with every price update. It is only the delivery channel to open WebSocket connections (`/ws`) and not a data source: prices, news, patterns, events and backtests are stored in their own tables with source and fetch time and are not touched.
- An error with one instrument no longer stops the other instruments in the price jobs (as was already the case for patterns, analyses and forecasts); it goes to the log.

## Getting started (Docker Compose)

Requirement: Docker with Compose.

```bash
cp .env.example .env        # .env lives in the project root, next to docker-compose.yml
# In .env set at least SESSION_SECRET, ADMIN_EMAIL and ADMIN_PASSWORD, then enter the API keys
docker compose up --build
```

**Note on `.env`:** Do not put comments after a value (`KEY=   # text`). Docker Compose would otherwise take the comment as the value. Put comments on a separate line above. If you copied your `.env` from an older `.env.example`, remove such comments or copy the template again. The backend treats values that start with `#` as unset (warning in the log), and invalid `IR_FEEDS`/`EQS_RSS_URL` appear on the Sources page as "invalid, disabled".

Then open `http://localhost:8080` in the browser (port via `WEB_PORT`). The first admin is created at startup from `ADMIN_EMAIL`/`ADMIN_PASSWORD`. This only happens on the very first start, as long as no admin exists; the placeholders from `.env.example` (`admin@example.com`, `change-me-now`) are rejected (notice in the log of the `api` container). An existing admin is never overwritten automatically, not even if you changed the password in the app. If `ADMIN_EMAIL` differs from the existing admin, a warning appears in the log.

If you changed `.env` only after the first start and cannot log in, this command applies the values from `.env` to the existing database (without deleting it):

```bash
docker compose run --rm api python -m app.admin_cli
```

Further users are created by an admin (`POST /api/users`); there is no open registration.

### User management (admin)

As an administrator the menu shows **Users**. There you can create accounts (email, display name, role), lock and unlock them and reset passwords. Procedure for a friend:

1. **Create account**: the dashboard shows a one-time password exactly once. It is not stored and not sent by email (there is no mail delivery), so pass it on yourself.
2. On first login the friend must set their own password (at least 10 characters); until then only that page is reachable. Every user can change their password later under their name at the top right; their other sessions are ended in the process.
3. **Lock** ends all sessions of the account immediately; login and live connection are no longer possible afterwards. **Reset password** creates a new one-time password and also ends all sessions.
4. The last active admin and your own account cannot be locked or demoted.

API keys only exist in the server's `.env`. No endpoint and no page delivers them to a browser (not even to admins); a test checks this for all GET routes. Some free data tiers only allow private use, so please check the terms of use before sharing (Sources page). The Claude budget applies to all users together. To update: `docker compose up --build` (migration `0008` runs at startup).

### Windows: line endings

The file `.gitattributes` enforces LF for scripts and configuration files that run in the Linux containers. In addition, `backend/Dockerfile` strips any CRLF from `entrypoint.sh` when building. If `exec ./entrypoint.sh: no such file or directory` occurred before, run this once in an existing clone after pulling:

```bash
git pull
git add --renormalize .
git status                  # should show nothing relevant
docker compose up --build -d
```

If files in the working directory still have CRLF: `git rm --cached -r . && git reset --hard` (discards local, uncommitted changes).

`.env` is never committed. Keys belong there exclusively. Keys appear neither in logs nor in status texts on the Sources page: log entries are sanitized centrally (`backend/app/log_redaction.py`), httpx's HTTP client logging is set to WARNING, and where the provider supports it the key goes in the header instead of the URL. Anyone who shared logs before this change or keeps logs from an older version should renew the affected keys with the provider.

## Development without Docker

```bash
cd backend && pip install -e ".[dev]" && pytest && ruff check . && mypy app
cd frontend && npm ci && npm test && npm run build
```

## Tests (Phase 5B)

Four levels, all run in CI (`.github/workflows/ci.yml`):

| Level | Command | What it checks |
|---|---|---|
| Backend units | `cd backend && pytest` | Adapters, pipeline, API, indicators, patterns with synthetic series with known results, Grundregel scan of the source texts |
| Pattern regression | `cd backend && pytest tests/regression` | Fixed candle fixtures (CSV) run through pattern detection; patterns, period, status, criteria values, confidence, scenario levels and zones are recorded in `tests/regression/golden/patterns.json` |
| Frontend units | `cd frontend && npm test` | Components and pages against a mocked API contract (Vitest) |
| End to end | `cd frontend && npm run e2e` | Playwright (Chromium) against the built frontend and a real backend |

**Pattern regression tests.** If a parameter or a detection rule changes, `test_golden_matches_current_engine` fails and shows the deviation as a diff. If the change is intended: `cd backend && UPDATE_GOLDEN=1 pytest tests/regression`, review the diff of `golden/patterns.json` in the PR and, if rules changed, increase `ALGO_VERSION` in `backend/app/analysis/params.py`. The 17 fixtures (13 pattern types, a failed and a not yet confirmed double bottom, two negative cases without a pattern, a random series with a fixed seed) are invented candles stored as CSV in `tests/regression/fixtures/`; `python -m tests.regression.make_fixtures` regenerates them (only when the fixtures are deliberately changed).

**End-to-end tests.** `npm run e2e` (in the `frontend` folder, run `npx playwright install chromium` once) starts a backend with a fresh SQLite database under `frontend/.e2e/` and builds and starts the frontend (`vite preview`). The backend runs with `DEMO_MODE=true` and is filled via `backend/app/e2e_seed.py` with **labeled sample data**: two instruments "Demo ... (sample data)" with invented candles (DEMOA with a confirmed double bottom, DEMOB with a double bottom in formation), two news items from two demo sources and a hard-coded pattern backtest. Patterns, indicator events and forecast are produced by the same services as in production. The seed refuses to run without `DEMO_MODE=true`. There are no keys and no access to real providers: the backend gets a proxy pointing nowhere, so GDELT and OpenFIGI appear as "offline" on the Sources page. With `E2E_PYTHON=<path to python>` you can set the backend's Python interpreter (default: `backend/.venv` or `python`), with `npx playwright test e2e/patterns.spec.ts` you can run a single test, and with `--ui` you can open the Playwright inspector.

Covered: login, logout and one-time password (`login.spec.ts`, `users.spec.ts`), search and watchlist, chart with periods and indicators, patterns with a full explanation (criteria with values, confidence, scenarios, backtest), forecast corridor with method and error measures, news with filters and all sources, the Sources page, and in `grundregeln.spec.ts` on every page the disclaimer (Grundregel 5), the demo banner (rule 6) and the absence of recommendation vocabulary (rule 1; the word list comes from `backend/app/grundregeln.py`). The login is in `frontend/e2e/helpers/auth.ts`; if the login changes, only this file needs adjusting.

## Server operation (Phase 5)

For continuous operation on a server (Tailscale or a public HTTPS address with an automatic certificate), updating with `./deploy/update.sh`, nightly database backup and restore: see [docs/operations.md](docs/operations.md). With `APP_ENV=production` the API only starts with its own values for `SESSION_SECRET` and `ADMIN_PASSWORD`.

## Layout

`backend/` (FastAPI, worker, Alembic, adapters), `frontend/` (with `e2e/` for Playwright) (Vite, React, TypeScript, Tailwind), `docs/api-contract.md` (API contract), `docs/grundregeln-check.md` (self-check per phase).
