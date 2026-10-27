"""Investor relations feeds of individual companies (RSS/Atom of the IR page): source "ir_feeds", one feed per stock.
Only the headline, a short excerpt and the link to the original page are taken over (no full text).

Off by default: the feed address and terms of use of each IR page must be checked before enabling.
Enable via .env: IR_FEEDS=AAPL|https://.../feed.xml,SAP.DE|https://.../rss.xml (symbol|address, https only).
The assignment to the stock is proven because the feed explicitly belongs to the configured company."""
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, NewsAdapter, NewsRecord, NewsTarget
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError, is_valid_https_url
from app.adapters.rss import parse_feed
from app.config import get_settings

log = logging.getLogger(__name__)


def parse_ir_feeds_checked(raw: str) -> tuple[dict[str, str], int]:
    """'SYM|https://url,SYM2|https://url2' -> ({'SYM': url}, number of invalid entries).
    Invalid: without symbol, not https, not a valid hostname."""
    out: dict[str, str] = {}
    invalid = 0
    for part in raw.split(","):
        if not part.strip():
            continue
        sym, _, url = part.strip().partition("|")
        sym, url = sym.strip().upper(), url.strip()
        if sym and is_valid_https_url(url):
            out[sym] = url
        else:
            invalid += 1
    return out, invalid


def parse_ir_feeds(raw: str) -> dict[str, str]:
    return parse_ir_feeds_checked(raw)[0]


class IrFeedsAdapter(ProbedHealth, NewsAdapter):
    key = "ir_feeds"
    poll_seconds = 900
    disabled_reason = "IR_FEEDS not set (check the feed address and terms of use of the IR page first)"

    def __init__(self, feeds: dict[str, str] | None = None, transport: httpx.BaseTransport | None = None,
                 **kw: Any) -> None:
        self._invalid = 0
        if feeds is None:
            self._feeds, self._invalid = parse_ir_feeds_checked(get_settings().ir_feeds)
            if self._invalid:
                log.warning("IR_FEEDS: %d invalid entry/entries ignored (format symbol|https://address)",
                            self._invalid)
                if not self._feeds:
                    self.disabled_reason = ("IR_FEEDS invalid (expected: SYMBOL|https://address, several separated by "
                                            "comma); source disabled")
        else:
            self._feeds = feeds
        self.http = ResilientHttp(base_url="", headers={"User-Agent": "Marktmuster-Dashboard (Informationstool)"},
                                  rate_per_min=6, transport=transport, **kw)

    def metadata(self) -> AdapterMetadata:
        n = len(self._feeds)
        return AdapterMetadata(
            key=self.key, name="Investor relations feeds", kind="news",
            description="News from the investor relations pages of individual companies (only feeds that "
            f"were explicitly configured; currently {n}"
            + (f", {self._invalid} invalid entries in IR_FEEDS ignored" if self._invalid else "")
            + "). Only headline, short excerpt and link to the "
            "original page.",
            homepage="", terms_url="", update_interval="every 15 min. (watchlist stocks with a feed)",
            delay_text="minutes after publication", requires_key=False, is_official=True)

    def is_configured(self) -> bool:
        return bool(self._feeds)

    def _probe(self) -> None:
        self.http.request("GET", next(iter(self._feeds.values())))

    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]:
        return self._fetch({s.upper(): s for s in symbols}, {}, since)

    def fetch_news_for(self, targets: list[NewsTarget], since: datetime) -> list[NewsRecord]:
        wanted = {t.symbol.upper(): t.symbol for t in targets if t.exchange in self.supported_exchanges}
        return self._fetch(wanted, {t.symbol.upper(): t.name for t in targets}, since)

    def _fetch(self, wanted: dict[str, str], names: dict[str, str], since: datetime) -> list[NewsRecord]:
        out: list[NewsRecord] = []
        errors: list[str] = []
        todo = [(k, u) for k, u in self._feeds.items() if k in wanted]
        for key, url in todo:
            try:  # a broken feed must not block the others
                resp = self.http.request("GET", url)
                records = parse_feed(resp.content, self.key, None, datetime.now(UTC))
            except SourceError as exc:
                errors.append(f"{key}: {exc}")
                continue
            publisher = f"Investor Relations {names.get(key) or wanted[key]}"
            out.extend(NewsRecord(
                external_id=r.external_id, url=r.url, title=r.title, excerpt=r.excerpt, published_at=r.published_at,
                fetched_at=r.fetched_at, source_key=self.key, language=None, publisher=publisher,
                symbols=(wanted[key],)) for r in records if r.published_at >= since)
        if todo and errors and len(errors) == len(todo):
            raise SourceError("Alle IR-Feeds fehlgeschlagen: " + "; ".join(errors))
        return out
