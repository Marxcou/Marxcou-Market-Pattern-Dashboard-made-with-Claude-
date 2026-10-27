"""Alpha Vantage News (optional, free: 25 requests per day). Only headline, excerpt and link are
taken over; the sentiment values from Alpha Vantage are deliberately not used (own, explained method)."""
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, NewsAdapter, NewsRecord
from app.adapters.http import PassiveHealth, ResilientHttp, SourceError
from app.adapters.news_common import clean_excerpt, clean_title
from app.api_usage import calls_today, count_call
from app.config import get_settings

DAILY_LIMIT = 20  # reserve below the 25 requests per day
CHUNK = 5


class AlphaVantageNewsAdapter(PassiveHealth, NewsAdapter):
    key = "alphavantage_news"
    supported_exchanges = ("XNYS", "XNAS")
    poll_seconds = 3600

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self._token = get_settings().alphavantage_api_key
        self.http = ResilientHttp(base_url="https://www.alphavantage.co", rate_per_min=5, transport=transport, **kw)
        self._cursor = 0

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="Alpha Vantage News", kind="news",
            description="Optional additional US news source. The free quota (25 requests per day) "
            "only covers a few stocks per hour; the stocks are queried in rotation.",
            homepage="https://www.alphavantage.co", terms_url="https://www.alphavantage.co/terms_of_service/",
            update_interval="hourly, in rotation (max. 20 requests/day)", delay_text="minutes", requires_key=True,
            is_official=True,
        )

    def is_configured(self) -> bool:
        return bool(self._token)


    def _budget_left(self) -> bool:
        return calls_today(self.key) < DAILY_LIMIT

    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]:
        if not symbols or not self._budget_left():
            return []
        start = self._cursor % len(symbols)
        chunk = (symbols[start:] + symbols[:start])[:CHUNK]
        self._cursor += CHUNK
        count_call(self.key)
        resp = self.http.request("GET", "/query", params={
            "function": "NEWS_SENTIMENT", "tickers": ",".join(chunk), "time_from": since.strftime("%Y%m%dT%H%M"),
            "limit": 50, "sort": "LATEST", "apikey": self._token})
        try:
            data = resp.json()
            if "feed" not in data:  # limit and key errors come as 200 with a text field
                info = str(data.get("Information") or data.get("Note") or "no data")
                raise SourceError("Alpha Vantage: " + info[:120])
            fetched = datetime.now(UTC)
            out = []
            for r in data["feed"]:
                ts = datetime.strptime(r["time_published"], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
                tags = tuple(t["ticker"] for t in r.get("ticker_sentiment", []) if t.get("ticker") in chunk)
                out.append(NewsRecord(
                    external_id=r["url"], url=r["url"], title=clean_title(r["title"]),
                    excerpt=clean_excerpt(r.get("summary")), published_at=ts, fetched_at=fetched,
                    source_key=self.key, language="en", publisher=r.get("source") or None, symbols=tags))
            return out
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceError("Unerwartetes Antwortformat") from exc
