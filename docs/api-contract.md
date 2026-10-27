# API contract (as of Phase 1B, extended per phase)

All paths are under `/api`, JSON. Login via the cookie `session` (httpOnly). Unsafe methods (POST/DELETE/...) need the header `X-CSRF-Token` with the value from `/api/auth/login` or `/api/auth/me`. Timestamps are ISO-8601 in UTC and always with a time zone (`Z` or `+00:00`); without one the browser would read them as local time. Time parameters with another offset are converted to UTC before comparison. The frontend formats in the Europe/Berlin time zone.

**Language of texts:** Texts written by the backend (explanations, labels, error details, source descriptions) are English by default. Identifiers and enum values such as `pattern_type`, `status`, `direction_if_confirmed`, criterion keys and key point roles are German domain identifiers and are the same in every language. The examples in this document show the English texts.

Every price/candle carries `source` (`key`, `name`, `homepage`, `terms_url`, `delay_text`) and `fetched_at` (Grundregel 2). Missing data is explained through `empty_reason` and never replaced by placeholders.

| Method/Path | Auth | Purpose |
|---|---|---|
| GET `/health` | no | Liveness |
| GET `/meta` | no | `demo_mode`, `timezone`, `disclaimer` |
| POST `/auth/login` `{email,password}` | no | Sets the cookie, returns `{user, csrf_token}` |
| GET `/auth/me` | yes | `{user, csrf_token}` |
| POST `/auth/logout` | yes | 204 |
| POST `/auth/change-password` `{current_password,new_password}` | yes | 204. At least 10 characters, must differ from the old one (400), wrong current password 400. Ends all other sessions of the account, sets `must_change_password=false` |
| GET `/users` | admin | `[{id,email,display_name,role,is_active,must_change_password,created_at}]` (never a password or hash) |
| POST `/users` `{email,display_name,role?,password?}` | admin | 201, as above plus `temporary_password` (only in this response; one is generated if `password` is missing). The account starts with `must_change_password=true`. 409 if the email is taken |
| PATCH `/users/{id}` `{is_active?,role?,display_name?}` | admin | Lock/unlock. Locking ends all sessions of the account. 409 for your own account and for the last active admin |
| POST `/users/{id}/reset-password` | admin | `{temporary_password}` (only in this response). Sets `must_change_password=true`, ends all sessions |

Further rules: Non-admins get 403 on all `/users` endpoints. Login of a locked account (with the right password) returns 403 "This account is locked"; with a wrong password 401. As long as `must_change_password=true`, every endpoint except `/auth/me`, `/auth/logout` and `/auth/change-password` returns 403 (header `X-Error-Code: password_change_required`); `UserOut` contains the flag. No endpoint returns API keys or password hashes (test `test_no_endpoint_returns_secrets`).

| Method/Path | Auth | Purpose |
|---|---|---|
| GET `/instruments/search?q=` | yes | Search by ticker, name, ISIN in locally stored instruments plus OpenFIGI (hits are stored, max. 25). If OpenFIGI fails, the local hits are returned. Response shape unchanged |
| GET `/instruments/{id}` | yes | Instrument + latest price (`quote` or `null`) |
| GET `/instruments/{id}/bars?timeframe=1m\|5m\|1h\|1d&start&end&limit` | yes | `{instrument, timeframe, bars[], empty_reason}` |
| GET `/watchlist` · POST `/watchlist {instrument_id}` · DELETE `/watchlist/{instrument_id}` | yes | The user's watchlist, instruments with latest price |
| GET `/sources` | yes | Sources with metadata and status (from adapter metadata + health) |
| WS `/ws` | cookie | Events `{id, type: quote\|news\|detection\|source_status, payload, created_at}` |

## Additions in 1B (no change to the response shapes)

- **`empty_reason` for `/bars`:** for XETRA instruments and `timeframe` ≠ `1d` it reads "No intraday data for XETRA on the free tier. Daily data (end of trading) is available." (`bars` is then empty). Otherwise as before, when no data has been stored yet.
- **Several sources per candle:** `/bars` returns exactly one candle per timestamp (for `1d` per calendar day), preferring Alpaca over Stooq over Yahoo. `source` names the actual source.
- **Quotes:** US: IEX real time (`source.key` `alpaca`, fallback `finnhub`), `delay_seconds` 0. XETRA: last daily close from Stooq (or Yahoo, if enabled), `delay_seconds` `null`, `source.delay_text` "End of trading (daily data)".
- **WS event `quote`:** `payload = {instrument_id, symbol, price, change_abs, change_pct, ts_utc, fetched_at, source_key, delay_seconds}`. At most about every 2 seconds per symbol; the frontend shows `ts_utc`/`fetched_at` as "last update".
- **`POST /watchlist`:** immediately triggers a history fetch in the background; the first candles may appear a few seconds later (empty chart with `empty_reason` until then).
- **`/sources`:** now contains `alpaca`, `finnhub`, `stooq`, `yahoo`, `openfigi`. Without an API key the status is `disabled` with `last_error` "API key not set"; `yahoo` (`is_official: false`) is `disabled` with "Switched off in .env (YAHOO_ENABLED=false)" until it is switched on. Pattern backtest runs name `stooq` or `yahoo` in `source.key`.

## Interfaces for the follow-up workstreams

- **1B (price data):** implements `PriceAdapter` (`backend/app/adapters/base.py`), registers it in `load_builtin_adapters()` (`adapters/registry.py`), hooks jobs into `JOBS` (`worker.py`), writes `Instrument`, `PriceBar`, `Quote` (always with `source_id` and `fetched_at`) and calls `events.publish(db, "quote", {...})`. Provides the provider search via `PriceAdapter.search_instruments` and extends `/instruments/search`.
- **1C (frontend):** replaces the placeholders in `frontend/src/App.tsx`, uses `frontend/src/lib/api.ts` (types mirror this contract) and `lib/format.ts` (localized formats). Layout including notice and demo banner stays in `components/Layout.tsx`.
- **New tables** come per workstream with their own Alembic migration (`cd backend && alembic revision --autogenerate`).

## Phase 2: news and sources (backend 2A/2B/2C)

All responses contain `source` objects (Grundregel 2). Sentiment and clusters are calculated; the original items (`items`) stay visible individually with source, link, publication and fetch time. Only the headline, a short excerpt (max. 300 characters) and the link are stored, never full texts.

| Method/Path | Auth | Purpose |
|---|---|---|
| GET `/news?instrument_id&source&sentiment&since&until&limit&cursor` | yes | `{items: NewsCluster[], total, next_cursor, empty_reason}`. `source` = source `key` (clusters with at least one item from this source). `sentiment` = `positiv\|neutral\|negativ`. Sorted by `first_published_at` descending. `limit` max. 100 (default 25). `cursor` is opaque (from `next_cursor`) |
| GET `/instruments/{id}/news?since&until&limit&cursor` | yes | Like `/news` for one instrument (chart markers: time = `first_published_at`) |
| GET `/news/counts?since` | yes | `{counts: {"<instrument_id>": n}, empty_reason}`: number of clusters per instrument on the user's watchlist since `since` (default: 24 h) |
| GET `/news/sentiment-status` | yes | Which method is currently active: `{active_method: "claude"\|"lexicon", claude_configured, budget_usd, spent_usd, month, fallback_reason}`. `fallback_reason` is for example "No API key set" or "Monthly limit reached", otherwise `null`. Additionally `claude_mode` (`batch`\|`direct`) and `pending_batches` (number of open Claude batches; in `batch` mode the word-list sentiment is shown until the result arrives) |
| WS `news` | cookie | `payload = {cluster_id, canonical_title, first_published_at, item_count, instrument_ids, is_new}` for a new cluster or when another source joins a cluster |

`NewsCluster`:

```json
{
  "id": 1,
  "canonical_title": "…",
  "first_published_at": "2026-09-28T12:00:00Z",
  "last_published_at": "2026-09-28T12:20:00Z",
  "item_count": 3,
  "instruments": [{"id": 5, "symbol": "AAPL", "match_method": "provider_tag"}],
  "sentiment": {
    "label": "positiv", "score": 0.5, "method": "lexicon", "model_name": "Financial word list (rule-based)",
    "model_version": "1", "rationale": "…", "evidence": ["record profit"], "created_at": "…"
  },
  "items": [{"id": 1, "title": "…", "excerpt": "…", "url": "https://…", "published_at": "…",
             "fetched_at": "…", "language": "en", "publisher": "Reuters", "source": {"key": "finnhub_news", "name": "Finnhub", "homepage": "…", "terms_url": "…", "delay_text": "…"}}]
}
```

- `items[].publisher`: original publisher or domain, when the provider passes items on (for example Finnhub, Marketaux, GDELT), otherwise `null`.
- `instruments[].match_method`: `provider_tag` (the provider delivers the symbol), `isin`, `ticker` (cashtag or ticker symbol in the title), `name` (company name in the title/excerpt).
- `sentiment` is `null` as long as it has not been calculated. `method` is `lexicon` or `claude`; `model_name` names the method or model used (core rule: state the model). `evidence` are verbatim quotes from the headline/excerpt (for `claude` checked against the text by the backend).
- Items with AI sentiment are to be labeled "AI-generated" in the UI (`method == "claude"`).
- `empty_reason` explains empty lists (for example "No items fetched yet. Sources without an API key are disabled, see the Sources page.").
- The filter `instrument_id` only uses substantiated assignments; items without an assignment only appear in `/news` without a filter.

### `/sources` (extension, additive)

In addition to the previous fields: `item_count_24h` (number of items stored in the last 24 h, only for `kind == "news"`, otherwise `null`). New in the list: the news sources `finnhub_news`, `sec_edgar`, `alphavantage_news`, `marketaux`, `gdelt`, optionally `ir_feeds` (investor relations feeds, off as long as `IR_FEEDS` is empty), optionally `eqs_news` and one `rss_<id>` per RSS feed, as well as the sentiment methods `sentiment_lexicon` (`kind: "reference"`) and `claude_sentiment` (`kind: "llm"`). Without a key or activation the status is `disabled` with `last_error` (reason).

## Phase 3A: indicators, indicator events, news to price (backend)

All values are calculated from stored candles (pure Python, deterministic, versioned parameters). Every response names the price sources of the input candles (`sources`, `fetched_at`) and `algo_version` (Grundregel 2). The series also contain the running candle (like `/bars`); events and moves only evaluate completed candles. There is no buy/sell language; directions are called `up`/`down` and only describe where the values stand.

### Indicator series for the chart

`GET /instruments/{id}/indicators?timeframe=1d&start&end&limit&sma=20,50&ema=12,26&rsi=14&macd=12,26,9&bb=20,2`

- Only requested indicators are calculated and delivered; every parameter may be omitted. `sma`/`ema`: comma-separated periods (max. 5 per type, 2 to 500). `rsi`: period. `macd`: `fast,slow,signal`. `bb`: `period,factor` (standard deviations, factor 0.5 to 5).
- `timeframe`, `start`, `end`, `limit` as for `/bars` (default `limit` 2000, max. 10000). The backend additionally loads 400 candles of lead-in for warm-up (not in the response). EMA/RSI start with the SMA of the first `n` values or the Wilder mean of the first `n` changes; values before the first valid point are `null`.
- The arrays are index-aligned with `timestamps` (UTC, same candles as `/bars` with the same `limit`/window; with several sources per candle the same priority applies as there).

```json
{
  "instrument_id": 5, "timeframe": "1d", "algo_version": "indicators-1",
  "timestamps": ["2026-09-25T00:00:00Z", "…"],
  "indicators": [
    {"key": "sma_20", "type": "sma", "params": {"period": 20}, "label": "SMA (20)", "panel": "price",
     "formula": "Arithmetic mean of the last 20 closing prices", "lines": {"value": [null, 141.2, "…"]}},
    {"key": "rsi_14", "type": "rsi", "params": {"period": 14}, "label": "RSI (14)", "panel": "own",
     "range": [0, 100], "reference_lines": [30, 70], "formula": "…", "lines": {"value": ["…"]}},
    {"key": "macd_12_26_9", "type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}, "panel": "own",
     "lines": {"macd": ["…"], "signal": ["…"], "histogram": ["…"]}},
    {"key": "bb_20_2", "type": "bollinger", "params": {"period": 20, "factor": 2.0}, "panel": "price",
     "lines": {"middle": ["…"], "upper": ["…"], "lower": ["…"]}}
  ],
  "sources": [{"key": "alpaca", "name": "…", "homepage": "…", "terms_url": "…", "delay_text": "…"}],
  "bars_fetched_at": "2026-09-29T11:00:00Z", "computed_at": "2026-09-29T11:00:05Z",
  "empty_reason": null
}
```

`panel`: `price` (in the price window) or `own` (own sub-window). `formula` is the plain-text formula for display. If candles are missing, `indicators` is empty and `empty_reason` explains it; if there are too few candles for a period, the series is entirely `null`.

### Indicator events

`GET /instruments/{id}/indicator-events?timeframe&type&since&until&limit&cursor` → `{events: IndicatorEvent[], next_cursor, empty_reason}`, sorted by `ts` descending, `limit` max. 200 (default 50).

`type`: `golden_cross`, `death_cross`, `rsi_divergence`, `bb_breakout`, `volume_spike`. `direction`: `up`, `down` or `null` (`volume_spike`).
- `golden_cross`/`death_cross`: SMA(50) crosses SMA(200) from below (`up`) or above (`down`).
- `rsi_divergence`: `up` = price makes a lower low, RSI a higher low; `down` = price higher high, RSI lower high.
- `bb_breakout`: the closing price is outside the upper (`up`) or lower (`down`) Bollinger Band (20, 2) for the first time.
- `volume_spike`: volume is clearly above the mean of the 20 preceding candles.

```json
{
  "id": 12, "instrument_id": 5, "timeframe": "1d", "type": "rsi_divergence", "direction": "up",
  "ts": "2026-09-17T00:00:00Z", "start_ts": "2026-09-03T00:00:00Z", "end_ts": "2026-09-17T00:00:00Z",
  "confirmed_at": "2026-09-24T00:00:00Z",
  "title": "RSI divergence (price lower, RSI higher)",
  "summary": "On 17 Sep the price formed a lower low (€141.85 instead of €142.10), while the RSI(14) formed a higher low (34.2 instead of 29.8).",
  "criteria": [{"name": "Lower price low", "rule": "Low 2 < low 1", "required": "< 142.10", "actual": "141.85", "passed": true}],
  "values": {"pivot1": {"ts": "…", "price": 142.10, "rsi": 29.8}, "pivot2": {"ts": "…", "price": 141.85, "rsi": 34.2}},
  "params": {"rsi_period": 14, "pivot_window": 5, "min_bars_apart": 5, "max_bars_apart": 60, "min_rsi_diff": 2.0},
  "algo_version": "indicator-events-1",
  "historical_stats": null,
  "historical_stats_reason": "No historical hit rate is calculated for indicator events yet.",
  "sources": [{"key": "stooq", "…": "…"}], "bars_fetched_at": "…", "detected_at": "…"
}
```

- `ts` is the time at which the event is marked in the chart (candle whose close meets the condition; for `rsi_divergence` the second extreme). `confirmed_at` is the candle from which it was recognizable (for divergences: `pivot_window` candles later; otherwise equal to `ts`). Only completed candles count; the running candle is never evaluated.
- `criteria[]`: every met condition with actual values (`required`/`actual` are ready-formatted texts; the numbers are additionally available unformatted in `values`).
- `historical_stats` is `null` until the pattern backtest (3C); the UI then shows `historical_stats_reason` instead of a hit rate (no invented numbers).

### Notable price moves and news published at the same time

`GET /instruments/{id}/move-links?timeframe&since&until&limit` → `{moves: NotableMove[], note, empty_reason}`.

A move is notable if the return of a candle (close to previous close) is more than 3 standard deviations from the returns of the 60 preceding candles (`return_z`) or the volume is more than 3 (`volume_z`). The news items are clusters of the same instrument whose first publication lies in the time window (`window_before_minutes`/`window_after_minutes` around `move_start`/`move_end`). `note` is always: "Coinciding in time, no statement about a cause." If there is no item in the window, `news` is empty (and displayed as such).

```json
{
  "id": 3, "instrument_id": 5, "timeframe": "1d", "move_start": "2026-09-24T00:00:00Z", "move_end": "2026-09-25T00:00:00Z",
  "return_pct": -4.1, "return_z": -3.6, "volume_z": 2.1, "reasons": ["return_z"],
  "params": {"lookback_bars": 60, "z_threshold": 3.0, "window_before_minutes": 1440, "window_after_minutes": 360},
  "algo_version": "move-links-1", "sources": [{"key": "stooq", "…": "…"}], "bars_fetched_at": "…", "detected_at": "…",
  "news": [{"cluster_id": 7, "canonical_title": "…", "first_published_at": "…", "time_offset_minutes": -95, "item_count": 3,
            "sources": [{"key": "finnhub_news", "…": "…"}]}]
}
```

`time_offset_minutes` = `first_published_at − move_start` (negative: before the start of the candle). The item itself (all sources) comes via `/instruments/{id}/news` or `/news` (`cluster_id`).

### WebSocket

New event of type `detection` (existing type) with `payload = {category: "indicator_event", event_id, instrument_id, timeframe, type, direction, ts}`. Pattern detections (3B) use the same type with `category: "pattern"`; the frontend distinguishes by `category`.

## Phase 3B: pattern detection (pattern engine)

Detection is rule-based and deterministic (`backend/app/analysis/`): the same candles + the same parameters produce the same detections. Every detection meets the duty to explain (Grundregel 3). There are **no** price targets and no "measured move" projections; scenarios only name the level from which a pattern counts as confirmed or invalid. The historical hit rate comes from the pattern backtest (3C); as long as it is missing, `backtest.status = "nicht_berechnet"` (not calculated) and all numbers are `null` (never estimated).

| Method/Path | Auth | Purpose |
|---|---|---|
| GET `/instruments/{id}/patterns?timeframe=1d\|1h&include_invalid=false&start` | yes | `PatternsResponse` (detections + support/resistance zones). Default: only `in_bildung` and `bestaetigt`; `include_invalid=true` also returns `ungueltig`. `start` (ISO) filters to detections with `end_ts >= start` |
| GET `/patterns/{detection_id}` | yes | One `PatternDetection` |
| GET `/patterns/catalog` | yes | All pattern types with description, criteria, weights and documented parameters (for "How is this calculated?") |
| GET `/patterns/counts` | yes | `{counts: {"<instrument_id>": n}, empty_reason}`: current patterns (`in_bildung` or confirmed within the last 20 candles) per instrument on the watchlist, timeframe `1d` |
| WS `detection` | cookie | `payload = {category: "pattern", detection_id, instrument_id, symbol, timeframe, pattern_type, name, status, previous_status, end_ts}` for a new detection or a status change |

`PatternsResponse`:

```json
{
  "instrument": {"id": 5, "symbol": "SAP", "name": "SAP SE", "isin": "DE0007164600", "exchange": "XETR", "currency": "EUR"},
  "timeframe": "1d",
  "detections": ["PatternDetection …"],
  "zones": ["SRZone …"],
  "data_basis": {"bars_from": "2021-09-29T00:00:00Z", "bars_to": "2026-09-28T00:00:00Z", "bar_count": 1256,
                 "last_fetched_at": "2026-09-28T20:05:00Z", "sources": [{"key": "stooq", "name": "Stooq", "homepage": "…", "terms_url": "…", "delay_text": "…"}]},
  "algo_version": "1.0.0",
  "params_hash": "3f2a9c1e",
  "computed_at": "2026-09-28T20:06:00Z",
  "empty_reason": null
}
```

`empty_reason` explains empty results, for example "No price data stored yet." or "Too few candles for pattern detection (at least 60, available 12)." or "Pattern detection has not yet run for this instrument." If candles exist but no pattern meets the criteria, `detections` is empty and `empty_reason` is "Currently no pattern meets all criteria."

`PatternDetection`:

```json
{
  "id": 42,
  "instrument_id": 5,
  "timeframe": "1d",
  "pattern_type": "doppelboden",
  "name": "Double bottom",
  "direction_if_confirmed": "aufwärts",
  "status": "in_bildung",
  "status_label": "Forming",
  "status_changed_at": "2026-09-17T00:00:00Z",
  "confirmed_at": null,
  "invalidated_at": null,
  "start_ts": "2026-08-20T00:00:00Z",
  "end_ts": "2026-09-17T00:00:00Z",
  "key_points": [
    {"role": "tief_1", "label": "Low 1", "ts": "2026-09-03T00:00:00Z", "price": 142.10},
    {"role": "zwischenhoch", "label": "Middle high", "ts": "2026-09-10T00:00:00Z", "price": 151.40},
    {"role": "tief_2", "label": "Low 2", "ts": "2026-09-17T00:00:00Z", "price": 141.85}
  ],
  "lines": [
    {"role": "nackenlinie", "label": "Neckline", "start": {"ts": "2026-09-03T00:00:00Z", "price": 151.40}, "end": {"ts": "2026-09-17T00:00:00Z", "price": 151.40}, "extend_right": true}
  ],
  "criteria": [
    {"key": "tief_abweichung", "name": "Deviation of the two lows", "rule": "The lows deviate by at most 1.5 % from each other",
     "threshold": 1.5, "actual": 0.18, "unit": "%", "actual_text": "Low 1: 142.10 on 03 Sep 2026, low 2: 141.85 on 17 Sep 2026, deviation 0.18 %",
     "required": true, "passed": true, "sub_score": 0.88, "weight": 0.35}
  ],
  "confidence": {
    "score": 0.74,
    "method": "Weighted mean of the sub-scores (0 to 1) of all criteria. A sub-score is 1 at the ideal value and falls linearly to 0 at the limit of the criterion.",
    "breakdown": [{"key": "tief_abweichung", "name": "Deviation of the two lows", "weight": 0.35, "sub_score": 0.88, "contribution": 0.308}]
  },
  "confirmation_level": 151.40,
  "invalidation_level": 139.72,
  "scenarios": [
    {"kind": "bestaetigung", "title": "Confirmation", "trigger_level": 151.40,
     "trigger_rule": "Closing price above the neckline at 151.40",
     "description": "If the price closes above 151.40, the double bottom counts as confirmed. Historically: see backtest.",
     "historical": null},
    {"kind": "scheitern", "title": "Failure", "trigger_level": 139.72,
     "trigger_rule": "Closing price below 139.72 (lower low minus 1.5 %)",
     "description": "If the price closes below 139.72 before the neckline is exceeded, the pattern counts as invalid.",
     "historical": null}
  ],
  "backtest": {
    "status": "nicht_berechnet", "run_id": null, "hit_rate": null, "sample_size": null, "ci_low": null, "ci_high": null,
    "base_rate": null, "not_better_than_random": null, "horizon_bars": null, "min_move_pct": null,
    "universe": null, "date_range": null, "computed_at": null, "survivorship_note": null, "verdict_text": null,
    "note": "The historical hit rate for this pattern has not been calculated yet."
  },
  "explanation": "Double bottom between 20 Aug 2026 and 17 Sep 2026: …",
  "data_basis": {"bars_from": "…", "bars_to": "…", "bar_count": 1256, "last_fetched_at": "…", "sources": ["SourceRef …"]},
  "params": {"max_tief_abweichung_pct": 1.5, "…": "…"},
  "algo_version": "1.0.0",
  "params_hash": "3f2a9c1e",
  "detected_at": "2026-09-17T20:06:00Z"
}
```

- **`pattern_type`** (name): `kopf_schulter` (head and shoulders), `kopf_schulter_invers` (inverse head and shoulders), `doppelhoch` (double top), `doppelboden` (double bottom), `dreieck_aufsteigend` (ascending triangle), `dreieck_absteigend` (descending triangle), `dreieck_symmetrisch` (symmetrical triangle), `flagge_aufwaerts`/`flagge_abwaerts` (flag after a rise/decline), `wimpel_aufwaerts`/`wimpel_abwaerts` (pennant after a rise/decline), `keil_steigend` (rising wedge), `keil_fallend` (falling wedge).
- **`direction_if_confirmed`**: `aufwärts` (upward) \| `abwärts` (downward) \| `offen` (open; symmetrical triangle: the direction only becomes clear from the breakout). Descriptive, no call to action.
- **`status`**: `in_bildung` (forming: neither the confirmation nor the invalidation level has been exceeded on a closing price), `bestaetigt` (confirmed), `ungueltig` (invalid). The event that occurs first counts; `confirmed_at`/`invalidated_at` name the candle. After a confirmation the status stays `bestaetigt` even if the price later falls back (`invalidated_at` is then set anyway).
- **`key_points[].role`** per pattern: for example `linke_schulter`, `kopf`, `rechte_schulter`, `nacken_1`, `nacken_2`, `hoch_1`, `hoch_2`, `tief_1`, `tief_2`, `zwischenhoch`, `zwischentief`, `fahnenstange_start`, `fahnenstange_ende`, `beruehrung_oben_n`, `beruehrung_unten_n`. `label` is the display text.
- **`lines`**: lines to draw (neckline, upper/lower boundary). `extend_right: true` means: extend to the last candle (where the current trigger level lies).
- **`criteria`**: all checked criteria with actual value. `required: true` are mandatory criteria (a detection only exists if all are met); `required: false` are quality criteria (for example volume trend) that only influence the confidence score and can also be `passed: false`. `threshold`/`actual` are numbers in `unit` (`%`, `Kerzen` (candles), `Preis` (price), `Faktor` (factor), `Anzahl` (count)), `actual_text` is ready-formatted.
- **`confidence.score`** 0..1 (the UI shows percent). `breakdown[].contribution = weight × sub_score`, sum = `score`. The weights per pattern are also in `/patterns/catalog`.
- **`scenarios[].kind`**: `bestaetigung` (confirmation) \| `scheitern` (failure); for the symmetrical triangle `ausbruch_oben` (breakout up) \| `ausbruch_unten` (breakout down). Always at least two. For sloped lines `trigger_level` is the value of the line at the last candle.
- **`scenarios[].historical`** and **`backtest`**: come from the table `backtest_runs` (workstream 3C writes it, `kind = "pattern"`, `subject = pattern_type`, same `timeframe` and `algo_version`; the latest run applies). With a run: `status = "berechnet"` (calculated), `hit_rate`/`base_rate`/`ci_low`/`ci_high` 0..1, `sample_size` number of cases, `not_better_than_random = true` if the 95 % interval covers the base rate; `verdict_text` for example "Historically not better than chance"; `survivorship_note` names the bias from today's index members; `historical` = `{share, sample_size, text}` from `metrics.scenarios[kind]`. Without a run: as above, everything `null`.
- **Pattern backtest (3C, implemented):** `python -m app.backtest_job` writes one run per pattern type (`timeframe = "1d"`; there is none for `1h`, which stays `nicht_berechnet`). `not_better_than_random` is `true` as soon as the lower bound of the 95 % interval is not above the base rate (the interval covers it **or lies entirely below it**). Additionally (additive) in the `backtest` block: `mean_return_pct`, `median_return_pct` (change after `horizon_bars` candles in the pattern direction, in %), `base_mean_return_pct` (the same over all trading days), `method` (description of the method), `source` (`{key, name, homepage, terms_url, delay_text, fetched_from, fetched_to}`). Without cases: `status = "berechnet"`, `sample_size = 0`, all rates `null`, `note` names the reason. The run's `metrics` also contain `hits`, `cases_open`, `cases_excluded`, `detections_seen`, `symbols_used`, `symbols_missing`, `scenarios`.
- **`explanation`**: deterministic explanation text from the calculated values (not an AI text).
- **Added during implementation (additive):** `status_reason` (reason for the status, for example "No confirmation by the end of the time limit on …"), `breakout_direction` (`aufwärts`/`abwärts` for the symmetrical triangle after a breakout, otherwise `null`), `formed_at` (last candle whose data goes into the detection; only from here was the pattern recognizable in real time, important for the backtest without look-ahead), `is_demo`. `status_changed_at` equals `formed_at` for `in_bildung`. `trigger_level` of sloped lines is the line value at the candle of the status change or (while forming) at the last candle. Without confirmation by the deadline (pattern width, at least 10, at most 60 candles; 10 candles for flags) or when the triangle apex is reached, a pattern becomes `ungueltig`.
- **Deadlines and levels per pattern:** double patterns and head and shoulders: confirmation by a closing price beyond the neckline, invalid beyond the outer extreme point (double) or the right shoulder (head and shoulders) plus 1.5 %. Triangles/wedges: the respective boundary line (extended). Flags/pennants: channel line in the direction of the flagpole; invalid beyond the extreme of the consolidation.
- **For 3C (backtest):** The engine is `app.analysis.engine.detect(bars, timeframe, params)` (pure numpy, no DB). `Detection.formed_idx`, `confirmed_idx`, `invalidated_idx` are candle indices; turning points carry `confirmed_idx`, so that a run on a truncated series yields the same turning points (test `test_pivots_are_confirmed_later_and_without_lookahead`).

`SRZone` (support and resistance zones from clusters of turning points):

```json
{
  "id": 7,
  "kind": "unterstuetzung",
  "kind_label": "Support zone",
  "lower": 139.80, "upper": 142.30, "center": 141.05,
  "touch_count": 4,
  "touches": [{"ts": "2026-03-12T00:00:00Z", "price": 140.10, "role": "tief"}],
  "first_touch": "2026-03-12T00:00:00Z", "last_touch": "2026-09-17T00:00:00Z",
  "criteria": ["Criterion …"],
  "confidence": {"score": 0.66, "method": "…", "breakdown": ["…"]},
  "explanation": "Zone between 139.80 and 142.30: 4 turning points since 12 Mar 2026 …"
}
```

Additionally per zone: `sources` (price sources of the candles used), `fetched_at`, `is_demo`. `kind` is relative to the last closing price: zone below = `unterstuetzung` (support), above = `widerstand` (resistance), price inside = `im_bereich` ("price inside the zone").

`/patterns/catalog` returns `{algo_version, params_hash, confidence_method, items: [...]}`; one entry: `{pattern_type, name, direction_if_confirmed, description, criteria: [{key, name, rule, required, weight}], params: [{key, value, unit, description}], algo_version}`.

## Phase 4A: forecasts, scenarios, forecast backtest (backend)

Forecasts exist only as a corridor (Grundregel 4): per step the quantiles 2.5/10/25/50/75/90/97.5 %, from which the bands 50 % (25–75), 80 % (10–90) and 95 % (2.5–97.5) follow. There is **no** endpoint for a single line; the median (`"50"`) is only the middle of the bands and is not drawn on its own. Everything is calculated from stored, completed daily candles (deterministic, fixed random seed per data state). Error measures come exclusively from a backtest on the stored candles; without a run `backtest.status = "nicht_berechnet"` and all numbers are `null` (never estimated).

| Method/Path | Auth | Purpose |
|---|---|---|
| GET `/instruments/{id}/forecast?timeframe=1d&horizon=20` | yes | `ForecastResponse`. `horizon` 1 to 20 candles (default 20) only shortens `steps`. Only `timeframe=1d`; otherwise 200 with `empty_reason`. 404 only for an unknown instrument |
| GET `/forecasts/methods` | yes | Description of all methods: `{algo_version, items: [{key, name, description, assumptions[], limitations[], params}]}` |

`ForecastResponse`:

```json
{
  "instrument_id": 5, "timeframe": "1d",
  "method": {"key": "monte_carlo_block_bootstrap", "name": "Monte Carlo simulation (block bootstrap)",
             "description": "…", "assumptions": ["…"], "limitations": ["…"],
             "params": {"lookback_bars": 750, "block_length": 10, "paths": 4000, "seed": 1234567}},
  "horizon_bars": 20,
  "based_on_until": "2026-09-28T00:00:00Z", "last_close": 151.2, "currency": "EUR",
  "generated_at": "2026-09-28T20:10:00Z", "algo_version": "forecast-1", "params_hash": "a1b2c3d4", "is_demo": false,
  "steps": [{"step": 1, "ts": "2026-09-29T00:00:00Z",
             "quantiles": {"2.5": 146.0, "10": 148.1, "25": 149.8, "50": 151.2, "75": 152.7, "90": 154.3, "97.5": 156.5}}],
  "bands": [{"level": 0.5, "lower": "25", "upper": "75"}, {"level": 0.8, "lower": "10", "upper": "90"},
            {"level": 0.95, "lower": "2.5", "upper": "97.5"}],
  "backtest": "ForecastBacktest …",
  "comparison": [{"method_key": "arima_1_1_0", "name": "ARIMA(1,1,0) on log prices", "description": "…",
                  "steps": ["… as above"], "backtest": "ForecastBacktest …", "metrics": ["… = backtest.metrics"]}],
  "pattern_scenarios": ["PatternScenarioLink …"],
  "median_line": {"quantile": "50", "name": "Median path of the model distribution", "description": "…",
                  "errors": [{"horizon_bars": 5, "sample_size": 142, "model": 2.1, "naive": 2.0, "unit": "%",
                              "better_than_naive": false}]},
  "example_paths": [{"percentile": 10, "label": "Example path (end value at the 10th percentile of the simulation)",
                     "steps": [{"step": 1, "ts": "2026-09-29T00:00:00Z", "close": 150.4}]}],
  "example_paths_note": "Individual simulated paths, selected by their end value …",
  "data_basis": {"bars_from": "…", "bars_to": "…", "bar_count": 1256, "last_fetched_at": "…", "sources": ["SourceRef …"]},
  "note": "Statistical scenarios from historical fluctuations, not a prediction and not investment advice.",
  "empty_reason": null
}
```

- **`steps[].ts`**: trading days simplified as weekdays (Mon–Fri) after `based_on_until`; holidays are not taken into account (stated in `method.limitations`).
- **`median_line`** describes the median path: the 50 % quantile from `steps` (no separate series of numbers), as the middle of the corridor. `errors` are the median errors (`median_abs_error`) of the forecast backtest per horizon, in percent of the price at the origin, with the naive reference; empty if there is no backtest. `null` without a forecast. The line is only shown together with the corridor, without a label at the end point (Grundregeln 1 and 4).
- **`example_paths`**: main method only, five actually simulated paths whose end value lies at the 10th/30th/50th/70th/90th percentile of all simulated end values (ascending). `steps` shortened like `horizon`. Examples, not more likely paths; empty without a forecast.
- **`method`** is the main method (corridor in the chart). **`comparison`** contains the comparison method ARIMA(1,1,0) with the same structure; the frontend can show it in the method panel.
- **`empty_reason`** for example "No price data stored yet.", "Too few candles for a forecast (at least 250, available 80).", "The forecast has not been calculated for this instrument yet.", "Forecasts currently exist only for daily candles." Then `steps` is empty and `method` is still set (the description stays viewable).

`ForecastBacktest` (rolling origin: on many past days a forecast is made using only the candles known until then and compared with the closing price that actually occurred later):

```json
{
  "status": "berechnet", "run_id": 17, "sample_size": 142, "horizon_bars": 20,
  "date_range": "2023-10-02 – 2026-08-31", "universe": "SAP (XETR), own history", "computed_at": "…", "is_demo": false,
  "coverage": [{"nominal": 0.5, "observed": 0.47}, {"nominal": 0.8, "observed": 0.76}, {"nominal": 0.95, "observed": 0.93}],
  "metrics": [
    {"key": "median_abs_error", "name": "Mean absolute error of the median", "model": 4.1, "naive": 4.3, "unit": "%"},
    {"key": "pinball_loss", "name": "Pinball loss (mean over all quantiles)", "model": 1.2, "naive": 2.1, "unit": "%"}
  ],
  "skill": 0.05, "dm_p_value": 0.21, "better_than_naive": false,
  "verdict_text": "Not demonstrably better than the naive reference \"price stays the same\" for the median (p = 0.21).",
  "by_horizon": [{"horizon_bars": 5, "sample_size": 142, "coverage": ["…"], "metrics": ["…"], "skill": 0.01,
                  "dm_p_value": 0.4, "better_than_naive": false}],
  "method_note": "…", "note": null
}
```

- Errors are in percent of the price at the forecast origin. `naive` = reference "price stays the same" (all quantiles = last closing price). `skill = 1 − model/naive` for the median error.
- `better_than_naive`: `true` only if the median error is smaller **and** the Diebold-Mariano test (one-sided, Newey-West variance) gives p < 0.05; otherwise `false` and `verdict_text` says so openly. `null` for a sample that is too small (< 30 origins).
- The main values apply to `horizon_bars` (20); `by_horizon` for 5, 10, 20.
- Without a run: `{"status": "nicht_berechnet", "run_id": null, "sample_size": null, …, "coverage": [], "metrics": [], "better_than_naive": null, "note": "The forecast quality has not been calculated for this instrument yet."}`.
- Stored in `backtest_runs` with `kind = "forecast"`, `subject` = method key, `universe` = instrument; the forecast refers to it via `backtest_run_id`.

`PatternScenarioLink` (link to the current patterns from 3B, only `in_bildung`):

```json
{
  "detection_id": 42, "pattern_type": "doppelboden", "name": "Double bottom", "status": "in_bildung",
  "scenarios": [
    {"kind": "bestaetigung", "title": "Confirmation", "trigger_level": 151.40,
     "model_probability": 0.31, "model_probability_text": "In 31 % of the simulated paths the price closes above 151.40 first within 20 trading days.",
     "historical": {"share": 0.58, "sample_size": 214, "text": "…"}},
    {"kind": "scheitern", "title": "Failure", "trigger_level": 139.72, "model_probability": 0.12, "model_probability_text": "…", "historical": null}
  ],
  "neither_probability": 0.57,
  "note": "The simulation does not know the pattern; it only shows how often the levels would be reached first given historical volatility. The historical rate comes from the pattern backtest."
}
```

`historical` is the same object as `scenarios[].historical` in `PatternDetection` (from the pattern backtest, otherwise `null`).

## Initial calculation after adding to the watchlist

`POST /watchlist` immediately starts price fetching, pattern detection, indicator events and forecast for the instrument in the background (instead of waiting for the periodic jobs). Until then `GET /instruments/{id}/bars`, `/patterns` and `/forecast` additionally report `pending: true` (with `empty_reason` in plain text) if the instrument was put on a watchlist in the last 15 minutes and the result is still missing. After that the normal empty state with a reason applies again. Unavailable timeframes (for example XETRA intraday on the free tier) are never `pending`, but name their reason.

## Explanation texts

| Method/Path | Auth | Response |
|---|---|---|
| GET `/patterns/{id}/explanation` | yes | Explanation text for the detection. 404 if the detection does not exist |
| GET `/instruments/{id}/forecast/explanation` | yes | Explanation text for the forecast (horizon 20 trading days). 404 with a reason as long as there is no forecast |

Response (both): `{text, source: "ki"|"vorlage", label, model_name, model_version, generated_at, cost_usd, fallback_reason, input_hash, budget: {month, spent_usd, budget_usd}}`. `source` is `"ki"` (AI) or `"vorlage"` (template).

- `source = "ki"`: text from Claude (`model_name`, `model_version` set), stored after the check; generated at most once per data state (hash of the input values), `cost_usd` is the cost of that generation.
- `source = "vorlage"`: deterministic text from the same values, `model_*` are `null`. `fallback_reason` names the reason: "No API key set", "Monthly limit reached", "AI service currently unreachable", "Sample data (demo mode): no AI texts" or "AI text rejected by the check (…)". Only the last case is stored (the call was paid for); the others are retried on the next request.
- The text only contains numbers and dates from the values of the detection or forecast, no recommendation language, no links. The source `claude_explain` (`kind: "llm"`) appears on the Sources page.
