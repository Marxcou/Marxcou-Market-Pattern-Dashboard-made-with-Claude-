"""Finnhub (free): US price as a fallback source when Alpaca does not deliver."""
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, BarRecord, PriceAdapter, QuoteRecord, Timeframe
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError, is_header_safe
from app.config import get_settings

log = logging.getLogger(__name__)


class FinnhubAdapter(ProbedHealth, PriceAdapter):
    key = "finnhub"
    supported_exchanges = ("XNYS", "XNAS")

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self._token = get_settings().finnhub_api_key.strip()
        if self._token and not is_header_safe(self._token):
            log.warning("FINNHUB_API_KEY: invalid characters, Finnhub stays disabled")
            self._token = ""
        self.http = ResilientHttp(base_url="https://finnhub.io/api/v1", rate_per_min=50, transport=transport,
                                  headers={"X-Finnhub-Token": self._token} if self._token else None, **kw)

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="Finnhub", kind="price",
            description="US prices as a fallback source (price, daily change). Historical candles are not in the "
            "free tier and are not obtained from here.",
            homepage="https://finnhub.io", terms_url="https://finnhub.io/terms-of-service",
            update_interval="retrieval every 60 sec.", delay_text="real time (US), mind the retrieval interval",
            requires_key=True,
        )

    def is_configured(self) -> bool:
        return bool(self._token)

    def _probe(self) -> None:
        self.http.request("GET", "/quote", params={"symbol": "AAPL"})

    def fetch_bars(
        self, symbol: str, exchange: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[BarRecord]:
        return []  # deliberately not supported (see description)

    def fetch_quote(self, symbol: str, exchange: str) -> QuoteRecord | None:
        resp = self.http.request("GET", "/quote", params={"symbol": symbol})
        try:
            q = resp.json()
            price, ts = float(q["c"]), int(q["t"])
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceError("Unexpected response format") from exc
        if price == 0 or ts == 0:  # Finnhub returns zeros for unknown symbols
            return None
        return QuoteRecord(
            symbol=symbol, exchange=exchange, price=price, ts_utc=datetime.fromtimestamp(ts, UTC),
            source_key=self.key, fetched_at=datetime.now(UTC), change_abs=q.get("d"), change_pct=q.get("dp"),
            delay_seconds=0,
        )
