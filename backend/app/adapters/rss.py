"""RSS/Atom feeds of reputable media and EQS ad-hoc announcements. Every feed is its own source.
Only the headline, a short excerpt and the link are taken over.

Feeds are off by default: the address and terms of use of each feed must be checked before enabling
(plan: 'not scraped if the terms forbid it'). Enable via .env:
RSS_ENABLED_FEEDS=tagesschau,cnbc (or 'all'); EQS via EQS_RSS_URL. The addresses below are suggestions and
were not retrieved in this environment; a wrong link shows up as status 'offline' on the Sources page."""
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from defusedxml import ElementTree as ET

from app.adapters.base import AdapterMetadata, NewsAdapter, NewsRecord
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError, is_valid_https_url
from app.adapters.news_common import clean_excerpt, clean_title
from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedConfig:
    id: str
    name: str
    url: str
    homepage: str
    terms_url: str
    language: str
    description: str
    poll_seconds: int = 600
    is_official: bool = False


FEEDS: tuple[FeedConfig, ...] = (
    FeedConfig("tagesschau", "tagesschau.de Wirtschaft", "https://www.tagesschau.de/wirtschaft/index~rss2.xml",
               "https://www.tagesschau.de", "https://www.tagesschau.de/infoservices/rssfeeds", "de",
               "Business news from ARD Tagesschau (general market news, without a fixed stock assignment)."),
    FeedConfig("cnbc", "CNBC Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html",
               "https://www.cnbc.com", "https://www.cnbc.com/nbcuniversal-terms-of-service/", "en",
               "General US financial and company news from CNBC."),
    FeedConfig("marketwatch", "MarketWatch Top Stories", "https://feeds.content.dowjones.io/public/rss/mw_topstories",
               "https://www.marketwatch.com", "https://www.marketwatch.com/site/rss", "en",
               "General US market news from MarketWatch."),
    FeedConfig("handelsblatt", "Handelsblatt Finanzen", "https://www.handelsblatt.com/contentexport/feed/finanzen",
               "https://www.handelsblatt.com", "https://www.handelsblatt.com/hilfe/rss", "de",
               "German financial and company news from Handelsblatt."),
)
EQS = FeedConfig("eqs", "EQS News (ad-hoc announcements)", "", "https://www.eqs-news.com",
                 "https://www.eqs-news.com/terms-of-use/", "de",
                 "Ad-hoc announcements and mandatory publications of German companies (EQS, formerly DGAP).",
                 poll_seconds=300, is_official=True)


def _text(el: Any, tag: str, ns: str = "") -> str:
    node = el.find(f"{ns}{tag}")
    return (node.text or "").strip() if node is not None and node.text else ""


def parse_feed(xml: bytes, source_key: str, language: str | None, fetched: datetime) -> list[NewsRecord]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise SourceError("Feed is not valid XML") from exc
    atom = "{http://www.w3.org/2005/Atom}"
    out: list[NewsRecord] = []
    if root.tag == f"{atom}feed":
        for e in root.findall(f"{atom}entry"):
            link_el = e.find(f"{atom}link")
            url = (link_el.get("href") if link_el is not None else "") or ""
            date = _text(e, "published", atom) or _text(e, "updated", atom)
            ts = datetime.fromisoformat(date.replace("Z", "+00:00")) if date else None
            if url and ts and _text(e, "title", atom):
                out.append(NewsRecord(external_id=_text(e, "id", atom) or url, url=url,
                                      title=clean_title(_text(e, "title", atom)),
                                      excerpt=clean_excerpt(_text(e, "summary", atom)),
                                      published_at=ts if ts.tzinfo else ts.replace(tzinfo=UTC), fetched_at=fetched,
                                      source_key=source_key, language=language))
        return out
    for item in root.iter("item"):
        url, title, date = _text(item, "link"), _text(item, "title"), _text(item, "pubDate")
        if not (url and title and date):
            continue  # not verifiable without link or time, therefore discarded
        try:
            ts = parsedate_to_datetime(date)
        except (TypeError, ValueError):
            continue
        out.append(NewsRecord(external_id=_text(item, "guid") or url, url=url, title=clean_title(title),
                              excerpt=clean_excerpt(_text(item, "description")),
                              published_at=ts if ts.tzinfo else ts.replace(tzinfo=UTC), fetched_at=fetched,
                              source_key=source_key, language=language))
    return out


class RssFeedAdapter(ProbedHealth, NewsAdapter):
    def __init__(self, feed: FeedConfig, *, enabled: bool, url: str | None = None,
                 transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self.feed = feed
        self.key = "eqs_news" if feed.id == "eqs" else f"rss_{feed.id}"
        self.poll_seconds = feed.poll_seconds
        self._url = url or feed.url
        self._enabled = enabled and bool(self._url)
        self.disabled_reason = (
            "EQS_RSS_URL not set (check feed address and terms of use first)" if feed.id == "eqs"
            else f"Not enabled (check the terms of use, then set RSS_ENABLED_FEEDS={feed.id})")
        if self._enabled and not is_valid_https_url(self._url):
            log.warning("%s: feed address is not a valid https address; source stays disabled",
                        "EQS_RSS_URL" if feed.id == "eqs" else f"Feed {feed.id}")
            self._enabled = False
            self.disabled_reason = ("EQS_RSS_URL invalid (expected: https://address); source disabled"
                                    if feed.id == "eqs" else f"Feed address of {feed.id} invalid; source disabled")
        self.http = ResilientHttp(base_url="", headers={"User-Agent": "Marktmuster-Dashboard (information tool)"},
                                  rate_per_min=6, transport=transport, **kw)

    def metadata(self) -> AdapterMetadata:
        f = self.feed
        return AdapterMetadata(
            key=self.key, name=f.name, kind="news",
            description=f"{f.description} Only headline, short excerpt and link.", homepage=f.homepage,
            terms_url=f.terms_url, update_interval=f"every {f.poll_seconds // 60} min.", delay_text="minutes",
            requires_key=False, is_official=f.is_official)

    def is_configured(self) -> bool:
        return self._enabled

    def _probe(self) -> None:
        self.http.request("GET", self._url)

    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]:
        resp = self.http.request("GET", self._url)
        records = parse_feed(resp.content, self.key, self.feed.language, datetime.now(UTC))
        return [r for r in records if r.published_at >= since]


def build_rss_adapters() -> list[RssFeedAdapter]:
    s = get_settings()
    wanted = {x.strip() for x in s.rss_enabled_feeds.split(",") if x.strip()}
    adapters = [RssFeedAdapter(f, enabled="all" in wanted or f.id in wanted) for f in FEEDS]
    adapters.append(RssFeedAdapter(EQS, enabled=bool(s.eqs_rss_url), url=s.eqs_rss_url))
    return adapters
