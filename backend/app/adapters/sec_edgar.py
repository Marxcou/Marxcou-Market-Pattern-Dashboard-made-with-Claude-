"""SEC EDGAR (official): US mandatory filings (8-K, 10-Q, 10-K, Form 4, 6-K, 20-F) per stock.
The SEC requires a contact address in the user agent and at most 10 requests per second."""
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, NewsAdapter, NewsRecord
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError, is_valid_contact_email
from app.adapters.news_common import clean_excerpt, clean_title
from app.config import get_settings

log = logging.getLogger(__name__)

FORMS = {"8-K", "10-Q", "10-K", "4", "6-K", "20-F"}
FORM_LABEL = {
    "8-K": "current report (Form 8-K)", "10-Q": "quarterly report (Form 10-Q)",
    "10-K": "annual report (Form 10-K)", "4": "insider filing (Form 4)",
    "6-K": "report of a foreign issuer (Form 6-K)", "20-F": "annual report of a foreign issuer (Form 20-F)",
}
TICKER_MAP_TTL = 24 * 3600


class SecEdgarAdapter(ProbedHealth, NewsAdapter):
    key = "sec_edgar"
    supported_exchanges = ("XNYS", "XNAS")
    poll_seconds = 600
    disabled_reason = "SEC_EDGAR_CONTACT_EMAIL not set (required in the SEC user agent)"

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        raw = get_settings().sec_edgar_contact_email.strip()
        # An invalid value (umlaut, not an email format) counts like a missing one: source 'disabled', backend runs
        self._email = raw if is_valid_contact_email(raw) else ""
        if raw and not self._email:
            log.warning("SEC_EDGAR_CONTACT_EMAIL is not a valid ASCII email address; SEC EDGAR stays disabled")
            self.disabled_reason = ("SEC_EDGAR_CONTACT_EMAIL invalid (ASCII characters only, format name@domain.com); "
                                    "source disabled")
        ua = f"Marktmuster-Dashboard {self._email}" if self._email else "Marktmuster-Dashboard"
        headers = {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}
        self.http = ResilientHttp(base_url="https://data.sec.gov", headers=headers, rate_per_min=240,
                                  transport=transport, **kw)
        self._ciks: dict[str, tuple[int, str]] = {}
        self._ciks_at = 0.0

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="SEC EDGAR", kind="news",
            description="Official US mandatory filings from the securities regulator SEC (8-K, 10-Q, 10-K, Form 4). "
            "Shown are form, company, time and link to the filing.",
            homepage="https://www.sec.gov/edgar", terms_url="https://www.sec.gov/os/webmaster-faq#developers",
            update_interval="every 10 min. (watchlist stocks)", delay_text="minutes after filing",
            requires_key=False,
        )

    def is_configured(self) -> bool:
        return bool(self._email)

    def _probe(self) -> None:
        self.http.request("GET", "/submissions/CIK0000320193.json")

    def _cik_map(self) -> dict[str, tuple[int, str]]:
        if not self._ciks or time.monotonic() - self._ciks_at > TICKER_MAP_TTL:
            resp = self.http.request("GET", "https://www.sec.gov/files/company_tickers.json")
            try:
                self._ciks = {str(v["ticker"]).upper(): (int(v["cik_str"]), str(v["title"]))
                              for v in resp.json().values()}
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                raise SourceError("Unerwartetes Antwortformat") from exc
            self._ciks_at = time.monotonic()
        return self._ciks

    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]:
        ciks = self._cik_map()
        out: list[NewsRecord] = []
        for sym in symbols:
            entry = ciks.get(sym.upper().replace(".", "-"))
            if entry is None:
                continue
            cik, company = entry
            resp = self.http.request("GET", f"/submissions/CIK{cik:010d}.json")
            try:
                recent = resp.json()["filings"]["recent"]
                fetched = datetime.now(UTC)
                for i, form in enumerate(recent["form"]):
                    if form not in FORMS:
                        continue
                    ts = datetime.fromisoformat(recent["acceptanceDateTime"][i].replace("Z", "+00:00"))
                    ts = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
                    if ts < since:
                        continue
                    acc = recent["accessionNumber"][i]
                    doc = recent["primaryDocument"][i]
                    items = recent.get("items", [""] * len(recent["form"]))[i]
                    desc = recent.get("primaryDocDescription", [""] * len(recent["form"]))[i]
                    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
                    excerpt = "Mandatory filing with the US securities regulator SEC."
                    if items:
                        excerpt += f" Inhalte (Items): {items}."
                    out.append(NewsRecord(
                        external_id=acc, url=url, title=clean_title(f"{company}: {FORM_LABEL.get(form, form)}"),
                        excerpt=clean_excerpt(excerpt + (f" Dokument: {desc}." if desc else "")),
                        published_at=ts, fetched_at=fetched, source_key=self.key, language="de",
                        publisher="SEC EDGAR", symbols=(sym,),
                    ))
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                raise SourceError("Unerwartetes Antwortformat") from exc
        return out
