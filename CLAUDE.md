# Market Pattern Dashboard (information tool, NOT investment advice)

Web dashboard: live news, live charts, rule-based pattern detection with full explanations, forecast scenarios with uncertainty bands. The UI is English by default with German available through a language switch (de-DE, Europe/Berlin); timestamps are stored in UTC.

## Core rules (Grundregeln; non-negotiable, for every session and every code state)

1. No buy or sell recommendations. No terms like "buy", "sell", "strong buy", "price target" (German: "Kaufen", "Verkaufen", "Kursziel") and no traffic-light signals that call for action. Neutral, descriptive language only.
2. Full source transparency: every news item, every price data point and every metric carries the provider name, original link, publication time and retrieval time. A "Sources" page describes the interval, delay and status of each source.
3. Patterns must be explained: name, location in the chart with time span, criteria met with actual values, confidence score with an explanation of the calculation, at least two scenarios with a confirmation level and an invalidation level, historical hit rate from a backtest with sample size.
4. Uncertainty is visible: forecasts only as a corridor with probability ranges; method and backtest error measures can be inspected.
5. Visible on every page: "This dashboard does not constitute investment advice. All analyses are automated, may be incorrect and are for information only." (German: "Dieses Dashboard stellt keine Anlageberatung dar. Alle Analysen sind automatisiert, können fehlerhaft sein und dienen ausschließlich der Information.")
6. No invented data. Missing data is shown clearly. Sample data only in the explicitly labeled demo mode.

Working method: at the end of each phase, check yourself that all core rules are met (result in `docs/grundregeln-check.md`). API keys only via `.env`, never in code and never in logs or stored status texts (see below).

## How the rules are enforced in code

- Rule 1: `backend/app/grundregeln.py` (list of forbidden terms) + `backend/tests/test_grundregeln.py` scans backend and frontend sources in CI. The same filter runs at runtime on AI texts.
- Rule 2: `source_id` and `fetched_at` are NOT NULL on every data table; API responses contain the `source` object. The Sources page is generated from the adapter metadata (`AdapterMetadata`).
- Rule 3: A detection may only be stored with a criteria list, confidence breakdown, both scenario levels and a backtest reference (test per pattern type).
- Rule 4: The forecast API returns quantile bands only.
- Rule 5: The notice is part of the app layout (`frontend/src/components/Layout.tsx`); a test checks every route.
- Rule 6: `DEMO_MODE` in `.env`; demo data carries `is_demo=true`, banner "DEMO MODE". Empty states name the reason and the last successful retrieval (`empty_reason`).

## Keys in logs (rule for every new adapter)

- Send keys as HTTP headers where possible (e.g. Finnhub `X-Finnhub-Token`), not as URL parameters.
- `backend/app/log_redaction.py` cleans every log entry (including tracebacks) of configured secrets and URL parameters such as `token`, `apikey`, `api_token`, `key`; httpx/httpcore logging is set to WARNING. Every process entry point calls `install()`.
- Status texts that end up in the DB or on the Sources page go through `redact()`. Test: `backend/tests/test_log_redaction.py`.

## Language

- Documentation, code comments and identifiers are English. UI text lives in `frontend/src/lib/messages.ts` as `[English, German]` pairs; add both when adding a string.
- Existing German domain identifiers (pattern types, status values such as `bestaetigt`, criterion keys, DB columns) are API identifiers and stay as they are; only user-visible text is translated.

## Structure

- `backend/` FastAPI (`app/main.py`), worker (`app/worker.py`), SQLAlchemy 2 + Alembic, adapters (`app/adapters/`)
- `frontend/` Vite + React + TypeScript + Tailwind
- `docs/api-contract.md` API contract between backend and frontend
- Analysis code is pure Python (numpy/pandas) without I/O, deterministic, with versioned parameters.

## Commands

- Start everything: `docker compose up --build` (after `cp .env.example .env`)
- Backend: `cd backend && pip install -e ".[dev]" && pytest && ruff check . && mypy app`
- Frontend: `cd frontend && npm ci && npm test && npm run build`
