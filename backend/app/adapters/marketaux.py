"""Marketaux (free: 100 requests per day, 3 articles per request): global news including German companies."""
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, NewsAdapter, NewsRecord, NewsTarget
from app.adapters.http import PassiveHealth, ResilientHttp, SourceError
from app.adapters.news_common import clean_excerpt, clean_title, xetra_symbol
from app.api_usage import calls_today, count_call
from app.config import get_settings

DAILY_LIMIT = 90  # reserve below the 100 requests per day
CHUNK = 5


class MarketauxAdapter(PassiveHealth, NewsAdapter):
    key = "marketaux"
    poll_seconds = 1200

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self._token = get_settings().marketaux_api_key
        self.http = ResilientHttp(base_url="https://api.marketaux.com", rate_per_min=20, transport=transport, **kw)
        self._cursor = 0

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="Marketaux", kind="news",
            description="Global financial news with company assignment, also for German stocks. The free "
            "tier has 100 requests per day with 3 articles each; the stocks are queried in rotation.",
            homepage="https://www.marketaux.com", terms_url="https://www.marketaux.com/terms",
            update_interval="every 20 min., in rotation (max. 90 requests/day)", delay_text="minutes",
            requires_key=True,
        )

    def is_configured(self) -> bool:
        return bool(self._token)


    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]:
        return self._fetch(symbols, since)

    def fetch_news_for(self, targets: list[NewsTarget], since: datetime) -> list[NewsRecord]:
        symbols = [xetra_symbol(t.symbol) if t.exchange == "XETR" else t.symbol for t in targets]
        return self._fetch(symbols, since)

    def _fetch(self, symbols: list[str], since: datetime) -> list[NewsRecord]:
        if not symbols or calls_today(self.key) >= DAILY_LIMIT:
            return []
        start = self._cursor % len(symbols)
        chunk = (symbols[start:] + symbols[:start])[:CHUNK]
        self._cursor += CHUNK
        count_call(self.key)
        resp = self.http.request("GET", "/v1/news/all", params={
            "symbols": ",".join(chunk), "filter_entities": "true", "language": "en,de",
            "published_after": since.strftime("%Y-%m-%dT%H:%M:%S"), "limit": 3, "api_token": self._token})
        try:
            fetched = datetime.now(UTC)
            out = []
            for r in resp.json()["data"]:
                ts = datetime.fromisoformat(r["published_at"].replace("Z", "+00:00"))
                tags = tuple(e["symbol"] for e in r.get("entities", []) if e.get("symbol") in chunk)
                out.append(NewsRecord(
                    external_id=r["uuid"], url=r["url"], title=clean_title(r["title"]),
                    excerpt=clean_excerpt(r.get("snippet") or r.get("description")), published_at=ts,
                    fetched_at=fetched, source_key=self.key, language=r.get("language"),
                    publisher=r.get("source") or None, symbols=tags))
            return out
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceError("Unerwartetes Antwortformat") from exc
