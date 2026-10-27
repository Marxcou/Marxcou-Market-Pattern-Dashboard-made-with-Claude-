"""Alpaca Market Data (Basic, free): US prices and history via the IEX feed.
IEX is a single exchange with a small share of volume; the price can differ from the consolidated price."""
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, BarRecord, PriceAdapter, QuoteRecord, Timeframe
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError, is_header_safe
from app.config import get_settings

log = logging.getLogger(__name__)

US_EXCHANGES = ("XNYS", "XNAS")
_TF = {"1m": "1Min", "5m": "5Min", "1h": "1Hour", "1d": "1Day"}


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class AlpacaAdapter(ProbedHealth, PriceAdapter):
    key = "alpaca"
    supported_exchanges = US_EXCHANGES

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        s = get_settings()
        key_id, secret = s.alpaca_api_key_id.strip(), s.alpaca_api_secret_key.strip()
        self._configured = bool(key_id and secret)
        if self._configured and not (is_header_safe(key_id) and is_header_safe(secret)):
            log.warning("ALPACA_API_KEY_ID/ALPACA_API_SECRET_KEY: invalid characters, Alpaca stays disabled")
            self._configured, key_id, secret = False, "", ""
            self.disabled_reason = "Alpaca key contains invalid characters (ASCII only, no spaces)"
        self.http = ResilientHttp(
            base_url="https://data.alpaca.markets",
            headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret},
            rate_per_min=150, transport=transport, **kw,
        )

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="Alpaca Market Data (IEX)", kind="price",
            description="US stocks: real-time prices via the IEX feed (one exchange, may differ from the consolidated "
            "price) "
            "and price history. Free tier.",
            homepage="https://alpaca.markets/data", terms_url="https://alpaca.markets/disclosures",
            update_interval="Live via WebSocket, retrieval every 60 sec.", delay_text="IEX real-time price",
            requires_key=True,
        )

    def is_configured(self) -> bool:
        return self._configured

    def _probe(self) -> None:
        self.http.request("GET", "/v2/stocks/snapshots", params={"symbols": "AAPL", "feed": "iex"})

    def fetch_bars(
        self, symbol: str, exchange: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[BarRecord]:
        params: dict[str, Any] = {
            "timeframe": _TF[timeframe], "start": start.astimezone(UTC).isoformat(),
            "end": end.astimezone(UTC).isoformat(), "limit": 10000, "feed": "iex", "adjustment": "split",
            "sort": "asc",
        }
        out: list[BarRecord] = []
        while True:
            body = self._json(self.http.request("GET", f"/v2/stocks/{symbol}/bars", params=params))
            fetched = datetime.now(UTC)
            for b in body.get("bars") or []:
                out.append(BarRecord(
                    symbol=symbol, exchange=exchange, timeframe=timeframe, ts_utc=parse_ts(b["t"]),
                    open=float(b["o"]), high=float(b["h"]), low=float(b["l"]), close=float(b["c"]),
                    volume=float(b["v"]), source_key=self.key, fetched_at=fetched,
                ))
            token = body.get("next_page_token")
            if not token:
                return out
            params["page_token"] = token

    def fetch_quote(self, symbol: str, exchange: str) -> QuoteRecord | None:
        body = self._json(self.http.request(
            "GET", "/v2/stocks/snapshots", params={"symbols": symbol, "feed": "iex"}))
        snap = body.get(symbol) or (body.get("snapshots") or {}).get(symbol)
        if not snap or not snap.get("latestTrade"):
            return None
        price = float(snap["latestTrade"]["p"])
        prev = (snap.get("prevDailyBar") or {}).get("c")
        return QuoteRecord(
            symbol=symbol, exchange=exchange, price=price, ts_utc=parse_ts(snap["latestTrade"]["t"]),
            source_key=self.key, fetched_at=datetime.now(UTC),
            change_abs=price - float(prev) if prev else None,
            change_pct=(price / float(prev) - 1) * 100 if prev else None, delay_seconds=0,
        )

    @staticmethod
    def _json(resp: httpx.Response) -> dict[str, Any]:
        try:
            data = resp.json()
        except ValueError as exc:
            raise SourceError("Response is not JSON") from exc
        if not isinstance(data, dict):
            raise SourceError("Unerwartetes Antwortformat")
        return data
