# Core rules check (Grundregel-Check)

The six core rules ("Grundregeln") are listed in [CLAUDE.md](../CLAUDE.md). This file records the self-check at the end of each phase.

## Phase 1A (foundation)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | `backend/tests/test_grundregeln.py` scans backend and frontend |
| 2 Source transparency | skeleton met | NOT NULL `source_id`/`fetched_at`, `source` in API responses; the Sources page follows in 2D, `/api/sources` exists |
| 3 Duty to explain | not applicable yet | no patterns until Phase 3 |
| 4 Uncertainty | not applicable yet | no forecasts until Phase 4 |
| 5 Notice on every page | met | `Layout.tsx`, one test per route in `frontend/src/app.test.tsx` |
| 6 No invented data | met | no sample data in the code; `empty_reason` instead of placeholders; `DEMO_MODE` banner |

## Phase 1C (frontend: login, watchlist, search, chart)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | Texts are neutral, colors only up/down; CI scan green |
| 2 Source transparency | met | `SourceTip` on price and chart (provider, link, value time and fetch time, delay, terms) |
| 5 Notice on every page | met | Test for `/`, `/login`, `/quellen`, `/instrument/1`, 404 |
| 6 No invented data | met | Empty states with `empty_reason` (chart), "No price available" (card), demo labeling on price/chart; news and pattern counters were shown as "not connected yet" |

## Phase 1B (price data backend)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | `test_grundregeln.py` runs over the new code |
| 2 Source transparency | met | Every candle/quote is only stored with `source_id` and `fetched_at` (`price_service.py`); `/bars` and quotes carry `source`; adapter metadata (interval, delay, key requirement) feeds `/sources`; health is actively checked |
| 3 Duty to explain | not applicable yet | no patterns until Phase 3 |
| 4 Uncertainty | not applicable yet | no forecasts until Phase 4 |
| 5 Notice on every page | unchanged (1A) | frontend layout |
| 6 No invented data | met | A failure/missing key leads to a status and an empty result, never to substitute values (`test_failing_adapter_falls_through_without_invented_data`); Stooq notice texts are not read as CSV; XETRA intraday shows `empty_reason`; the IEX deviation and "end of trading" are in the source metadata |

Open/honest: The adapters were tested against simulated responses (mock transport), not against the real services, because there are no keys in this environment. Endpoints and fields follow the provider documentation; a run with real keys is the next verification step.

## Phase 2 (news backend)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | `test_grundregeln.py` runs over the new code; generated rationales (word list) are checked for forbidden terms (`test_lexicon_output_has_no_recommendation_language`); Claude answers with forbidden terms in the rationale or quote are discarded (`test_claude_verify_rejects_invented_quotes_and_forbidden_language`). Quotes from original headlines are shown unchanged |
| 2 Source transparency | met | `news_items` and `news_instruments` have NOT NULL `source_id`/`fetched_at`; every item delivers provider, link, publication and fetch time (and the original publisher if known); clusters list all sources; sentiment states method and model and has its own source on the Sources page; `/api/sources` shows description, interval, delay, status and items of the last 24 h |
| 3 Duty to explain | not applicable yet | no patterns until Phase 3 (sentiment carries its own rationale with verbatim evidence) |
| 4 Uncertainty | not applicable yet | no forecasts until Phase 4 |
| 5 Notice on every page | unchanged | frontend layout |
| 6 No invented data | met | Without key/activation: status `disabled` with a reason, no substitute items; the failure of one source stays local; items without a verifiable date or link are discarded; `empty_reason` states the reason and the last successful fetch |

Open/honest:
- All adapters were only tested against simulated responses (mock transport); there are no keys in this environment, and the sandbox cannot reach media feeds. Endpoints and fields follow the provider documentation from memory; a run with real keys is the next verification step.
- Investor relations feeds (`IR_FEEDS`): no address is preset, feeds are off until the project owner has checked and entered the address and terms of use of each IR page.
- RSS addresses and terms of use (tagesschau, CNBC, MarketWatch, Handelsblatt, EQS) are **not verified**. The feeds are therefore off by default and have to be enabled deliberately.
- The sentiment word list is a small list of our own, not Loughran-McDonald (the license terms of the original were not checked). Its accuracy was not measured against labeled data.
- Daily quotas (Marketaux, Alpha Vantage) are counted in memory; a worker restart resets the counter.
- Claude calls are made one by one (not via the Batch API), so costs are at the upper end of the estimate in the plan; the cap still applies strictly.

## Phase 3A (indicators, indicator events, news to price, backend)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | `test_grundregeln.py` scans the new code; all generated titles, summaries and criteria are checked for forbidden terms in the test `test_every_event_carries_explanation_and_neutral_language`; directions are called `up`/`down` and only describe where the values stand |
| 2 Source transparency | met | Indicator responses, events and moves state `sources` (provider, link, terms, delay) and `bars_fetched_at`; tables have NOT NULL `source_id`/`fetched_at`; linked news items carry all sources of their cluster |
| 3 Duty to explain | met for indicator events, as far as applicable | Every event stores criteria with rule, required value and actual value as well as parameters and version (test per event type). Scenarios, confidence score and backtest hit rate belong to chart patterns (3B/3C) and are not intended for indicator events; `historical_stats` is `null` with an explicit reason instead of invented numbers |
| 4 Uncertainty | not applicable yet | no forecasts until Phase 4 |
| 5 Notice on every page | unchanged | frontend layout |
| 6 No invented data | met | Without volume from the source there are no volume events; the running candle is never evaluated; empty responses carry `empty_reason`; series that are too short return `null` values instead of estimates; no sample data |

Open/honest:
- The parameters (SMA 50/200, RSI 14, pivot window 5, z threshold 3, time windows for news) are common defaults, not optimized on data. The time windows of the news assignment are a fixed choice without empirical verification.
- The indicators were tested against known reference values (the StockCharts RSI example) and analytical cases, not against another library on real data. A run with real price data is still pending.
- Bollinger Bands use the population standard deviation (ddof=0), as is usual in the literature; other charting tools may differ slightly.
- Support/resistance zones from the plan (3A) belong to the pattern engine (3B) and are not included here.

## Phase 3D (frontend: indicators, patterns, explanation panel)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | `test_grundregeln.py` runs over the new code. Colors are purely descriptive (patterns violet, events cyan), no traffic lights. Confirmation and invalidation levels are explicitly labeled as not price forecasts |
| 2 Source transparency | met | Below the chart are the price sources, fetch time, method version and formula of the displayed indicators; patterns, events and moves each have a collapsible source box with `SourceTip` |
| 3 Duty to explain | met (display) | `PatternPanel` shows name, period, key points, criteria with actual values, confidence with calculation and breakdown, at least two scenarios with levels and the backtest. If one of these parts is missing, a red warning "incompletely explained" appears (`patterns.test.tsx`) |
| 4 Uncertainty | not applicable yet | Forecasts follow in Phase 4 |
| 5 Notice on every page | unchanged | Layout, test over all routes |
| 6 No invented data | met | Missing endpoints (404), a missing backtest, missing indicator values (the warm-up phase stays empty) and unsupported timeframes (patterns only 1d/1h) are shown with a reason; never placeholder values |

Open/honest:
- The interface was built against the contract from the branches `phase-3a-indicators` and `phase-3-pattern-engine` and checked with simulated responses (Vitest and a visual check with mock data in the browser), not against the running backend.
- The warning threshold "small sample" (fewer than 30 cases) is an assumption of the interface, not a value from the backtest.
- The contract for the pattern backtest (3C) is still pending; the frontend reads the fields from 3B (`backtest`).
- Claude sentiment runs via the Batch API by default (half price, delayed results, word-list sentiment with a visible method until then). As in Phase 2 only tested against simulated responses; the batch response format follows the provider documentation and still has to be checked with a real key.

## Phase 3B (pattern engine, backend)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | `test_grundregeln.py` runs over the new code; all generated texts (criteria, scenarios, status, explanation) are checked per pattern type for forbidden terms (`test_explanation_duty_for_every_pattern_type`). Directions are called `aufwärts`/`abwärts`/`offen`. There are no price targets and no measured-move projection; scenarios only state the confirmation or invalidation level |
| 2 Source transparency | met | `pattern_detections` and `sr_zones` have NOT NULL `source_id`/`fetched_at` plus `source_ids`; the API delivers `data_basis` (period, candle count, last fetch, sources) per response and per detection |
| 3 Duty to explain | met (backend), hit rate follows with 3C | Every detection has name, period, key points, lines, all criteria with rule and actual value, confidence with method and breakdown (sum = score), at least two scenarios with levels and a `backtest` block. Test per pattern type (13 types). The hit rate comes from `backtest_runs`; as long as 3C has not run it explicitly says "not calculated" |
| 4 Uncertainty | not applicable yet | Forecasts follow in Phase 4 |
| 5 Notice on every page | unchanged | frontend layout |
| 6 No invented data | met | No estimated hit rate; the running candle is not evaluated; volume criteria are dropped without volume data (weights are visibly redistributed); empty responses state the reason (`empty_reason`: not run yet, too few candles, no intraday data for XETRA, no pattern meets the criteria) |

Open/honest:
- Parameters (for example 1.5 % deviation of the lows, ATR factor 2, criteria weights) are reasoned choices from common literature, not optimized on data. Whether they separate sensibly only becomes clear through the backtest (3C).
- Tested with synthetic price series with known results and a random series (runtime about 0.2 s for 1,300 candles), not with real price data.
- Several readings of the same price movement are possible (for example double bottom and triangle over the same turning points); both are shown with their own reasoning. Within a pattern family only the detection with the highest confidence remains in case of overlap.
- Detections at the right edge can change with new candles (for example a triangle gets another turning point); they are then recalculated and receive a new ID.

## Phase 3C (pattern backtest)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | `test_grundregeln.py` runs over the new code. Result texts only describe shares ("In 35.3 % of 17 cases detected in real time the pattern was confirmed", "The 95 % interval covers the base rate"); no call to action |
| 2 Source transparency | met | Every run stores the source (name, link, terms of use, delay), fetch period, period of the candles, values used and missing values with a reason; the API delivers `source`, `method`, `universe`, `date_range`; the panel shows them under "How was this calculated?" |
| 3 Duty to explain | met once the job has run with real data | Hit rate, sample size, 95 % interval, base rate, mean change and scenario shares per pattern type; "Historically not better than chance" also when the rate is below the base rate |
| 4 Uncertainty | met (for patterns) | Wilson interval, note on a small sample (below 30), note on non-independent cases and survivorship bias |
| 5 Notice on every page | unchanged | frontend layout |
| 6 No invented data | met | The job only stores what a real price source delivered and aborts without storing when there is no data (`test_job_without_data_stores_nothing`). Without cases the rate stays `null`. The running daily candle is not used. Tests use synthetic series only in the test database |

Open/honest:
- Not yet run with real data (there is no Stooq key here). Until the project owner starts the job, the dashboard keeps showing "not calculated".
- The hit definition (5 % in 20 candles) and the parameters of pattern detection are fixed choices, not optimized on data. Anyone who changes them after seeing the result risks overfitting.
- Whether Stooq adjusts for splits and dividends has not been checked; jumps above 40 % are therefore excluded and counted.
- Step size 5 candles: a case can start up to 4 candles later than with a daily evaluation (never earlier). `--step 1` is more precise but about five times slower.

## Fix: backtest and daily data with Yahoo when Stooq is missing

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | New texts only name the source and the missing setup; `test_grundregeln.py` runs over them |
| 2 Source transparency | met | A backtest run uses exactly one source, stored in `metrics.source` and in the text "Daily data from …"; the pattern view shows "Yahoo Finance (unofficial)" (`test_backtest_with_yahoo_records_yahoo_as_source`). Yahoo appears on the Sources page as unofficial with terms of use |
| 3 Duty to explain | unchanged | |
| 4 Uncertainty | unchanged | |
| 5 Notice on every page | unchanged | |
| 6 No invented data | met | Without a configured source the job aborts with a notice (`test_job_refuses_without_any_daily_source`). Yahoo days with missing values are skipped, HTML or error responses are never read as prices (`test_yahoo_unknown_symbol_is_empty_and_bad_answers_are_errors`) |

Open/honest:
- The Yahoo retrieval is only tested against reconstructed responses; Yahoo is not reachable from this environment. The first real run on the owner's machine will show whether the endpoint delivers without login.
- Yahoo prices are split-adjusted, not dividend-adjusted. Results from Stooq and Yahoo are therefore not exactly comparable; every run names its source.

## Phase 4A (forecasts, scenarios, forecast backtest, backend)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | `test_grundregeln.py` runs over the new code. Texts only describe shares of simulated paths and error measures ("closes above 151.40 first"); no price targets, no single value as an expectation |
| 2 Source transparency | met | Every forecast stores `source_ids`, `fetched_at`, period and candle count; the API delivers `data_basis` with sources. Backtest runs store period, instrument, parameters and `source_ids` |
| 3 Duty to explain | unchanged, extended | Pattern scenarios additionally show the simulated share next to the historical rate from the pattern backtest, with the note that the simulation does not know the pattern |
| 4 Uncertainty | met (backend) | The API only delivers quantiles per step (bands 50/80/95 %), no line endpoint. Method with assumptions and limits (`/forecasts/methods`), coverage, median error and pinball loss against "price stays the same", Diebold-Mariano p-value and an open verdict when the model is not better (tests `test_backtest_random_walk_is_not_better_than_naive`, `test_backtest_detects_skill_on_predictable_series`) |
| 5 Notice on every page | unchanged | frontend layout; the API additionally delivers `note` ("no prediction and no investment advice") |
| 6 No invented data | met | Error measures only from a backtest on stored candles, otherwise `"nicht_berechnet"` (not calculated) with `null`; below 30 test points no verdict (`better_than_naive: null`); the running candle is never included; outdated pattern probabilities are not shown; demo data is marked `is_demo` |

Open/honest:
- Tested only with synthetic series (random paths with a fixed seed, AR(1) series). Real coverage and error measures only exist after a run with real price data on the owner's machine.
- On a pure random path the main method is, as expected, not better than "price stays the same" for the median (the trend is removed). Its value lies in the width of the bands; `method_note` says so openly.
- Parameters (750 days lookback, block length 10, 20 days horizon, test point every 5 days) are common choices, not optimized. ARIMA is deliberately only (1,1,0) without order selection, so that no additional library (statsmodels) is needed.
- Future trading days are counted as weekdays; holidays are missing. For sloped pattern lines the level of the last candle is held constant over the horizon.
- Overlapping horizons make the test points dependent; the Diebold-Mariano test accounts for this with Newey-West, but the confidence level remains an approximation.

## Phase 4B (frontend: forecast corridor, scenario levels, method and backtest panel)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | `test_grundregeln.py` runs over the new code. Bands are graded in a single blue, scenario levels are only labeled ("Confirmation", "Failure"), no traffic lights, no price targets |
| 2 Source transparency | met | The panel states data state, creation time, method and version and shows the price sources as `SourceTip` |
| 3 Duty to explain | unchanged | Scenario levels come from `PatternDetection`; the comparison with the corridor only states the position, no probability; simulated path shares and the historical rate are shown separately and labeled next to each other |
| 4 Uncertainty | met (display) | Only bands 50/80/95 % (`PriceChart`: nested areas, no line, no median either). Method, assumptions, limits, parameters, coverage, error measures against "price stays the same", significance test and result per horizon are viewable; "historically not demonstrably better" is stated openly (`forecast.test.tsx`) |
| 5 Notice on every page | unchanged | Layout |
| 6 No invented data | met | A missing forecast (with `empty_reason`), incomplete steps (discarded), a missing backtest, non-daily candles and demo data are shown explicitly; never placeholder values |

Open/honest:
- Built against the contract from the branch `phase-4a-forecasts` and checked with simulated responses (Vitest, visual check of the nested bands in the browser with test data), not against the running backend.
- The classification "close to the target" of the coverage (deviation up to 5 percentage points) and the warning threshold "small sample" (below 30) are assumptions of the interface.
- The horizons 5/10/20 follow the backend limit of 20 candles. `GET /forecasts/methods` is not used yet; the method description comes from the forecast response.

## Phase 5B (tests: end to end, pattern regression)

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | additionally checked | `e2e/grundregeln.spec.ts` reads the visible text of every page and looks for the word list from `backend/app/grundregeln.py` (single source); also panels for patterns and forecast |
| 2 Source transparency | additionally checked | E2E opens the source details of price, chart and news items (provider, delay, fetch time, terms of use) and checks the Sources page: interval, delay, status, reason for disabled or unreachable sources |
| 3 Duty to explain | additionally checked | E2E: name, location with period, criteria table with values, confidence including calculation, at least two scenarios, both levels, backtest with sample. Regression test: every detection of every fixture meets the duty to explain |
| 4 Uncertainty | additionally checked | E2E: legend 50/80/95 %, method, coverage and error measures against "price stays the same" |
| 5 Notice on every page | automated | E2E checks the exact wording on login, watchlist, chart, news, sources and an unknown page; if the notice is removed, the test fails (tried out) |
| 6 No invented data | met | E2E data can only be created with `DEMO_MODE=true`, is called "sample data", carries `is_demo` and shows the banner; no provider access during the test run |

Open/honest:
- The test data and the pattern backtest in the E2E runs are invented sample values; they check the display, not the quality of detection or forecast.
- No test checks the drawing in the chart (canvas) in terms of content, only that it renders; pattern markers and corridor areas remain a visual check.
- The golden file records the current state of the (untuned) default parameters. It says "unchanged", not "correct".
- Three bugs were noticed while writing the tests and fixed: logging out had no effect (`qc.clear()` removed the query "me"), every access line in the uvicorn log failed in the log sanitizer, and a newly added stock showed "0 patterns" until the next fetch.

Explanation texts (AI, point 6 of the specification): Rule 1 is enforced at runtime (`explain_facts.validate`: word list from `grundregeln.py` plus phrases such as "recommend"; on a hit the template applies). Rule 3/4: the text only names values of the detection or forecast; every number and date is checked against the values, and if the hit rate is missing the text says so. Rule 6: no AI texts for demo data; AI text and template are labeled separately (tests `test_explanations.py`, `aiExplanation.test.tsx`, E2E `patterns.spec.ts`). Open: whether the texts are understandable for laypeople has not been assessed with a real key yet.

## Median path and example paths in the forecast

| Rule | Status | Evidence |
|---|---|---|
| 1 No recommendation language | met | The line is called "Median path of the model distribution", the description says "not an expected price". No end-value label in the chart (`lastValueVisible: false`), the median at the horizon does not appear as a single number in the panel (`forecast.test.tsx`). `test_grundregeln.py` and the E2E word list run over the new text |
| 2 Source transparency | unchanged | Line and paths come from the same forecast as the corridor (same data state, same sources) |
| 3 Duty to explain | unchanged | |
| 4 Uncertainty | met | Median and example paths are only drawn together with the corridor; without a corridor the switches disappear too (Vitest and E2E). Next to the line is its backtest error per horizon with sample and the reference "price stays the same"; if the backtest is missing it says "not available". Example paths are labeled as equally unlikely examples and chosen by the percentile of the end value, not by appearance |
| 5 Notice on every page | unchanged | Layout |
| 6 No invented data | met | Example paths are real paths of the stored simulation (a test compares values), incomplete ones are discarded; the median is the existing 50 % quantile |

Open/honest:
- The median of the main method is almost horizontal because the trend is removed. That is deliberate: the method has no demonstrable directional information historically, so a curved line would be invented.
- Drawing on the canvas was only checked by screenshot.
