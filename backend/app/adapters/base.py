"""Adapter interfaces. Exactly one adapter per data source (phases 1B/2 implement them).

Rules for every implementation:
- Every returned record carries source_key and fetched_at (core rule 2).
- If the API key is missing or the source is unreachable, this is reported via health()
  and NO substitute data is invented (core rule 6).
- Rate limits, retry/backoff and circuit breaker live in the adapter; an outage stays local.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

SourceKind = Literal["price", "news", "llm", "reference"]
SourceStatus = Literal["online", "degraded", "offline", "disabled"]
Timeframe = Literal["1m", "5m", "1h", "1d"]


@dataclass(frozen=True)
class AdapterMetadata:
    """Everything the 'Sources' page shows. It is generated exclusively from this."""

    key: str
    name: str
    kind: SourceKind
    description: str
    homepage: str
    terms_url: str
    update_interval: str  # e.g. "Live via WebSocket", "every 5 min."
    delay_text: str  # e.g. "15 min. delayed", "end of trading"
    requires_key: bool
    is_official: bool = True


@dataclass(frozen=True)
class Health:
    status: SourceStatus
    checked_at: datetime
    last_success_at: datetime | None = None
    message: str | None = None


@dataclass(frozen=True)
class BarRecord:
    symbol: str
    exchange: str
    timeframe: Timeframe
    ts_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    source_key: str
    fetched_at: datetime


@dataclass(frozen=True)
class QuoteRecord:
    symbol: str
    exchange: str
    price: float
    ts_utc: datetime
    source_key: str
    fetched_at: datetime
    change_abs: float | None = None
    change_pct: float | None = None
    delay_seconds: int | None = None


@dataclass(frozen=True)
class InstrumentRecord:
    symbol: str
    name: str
    exchange: str
    currency: str
    source_key: str
    fetched_at: datetime
    isin: str | None = None
    figi: str | None = None


@dataclass(frozen=True)
class NewsRecord:
    external_id: str
    url: str
    title: str
    excerpt: str  # max. ~300 characters, never the full text
    published_at: datetime
    fetched_at: datetime
    source_key: str
    language: str | None = None
    publisher: str | None = None  # original publisher/domain, if the provider passes news on
    # Symbols supplied by the provider (origin "provider_tag"). Convention: US symbols unchanged ("AAPL"),
    # XETRA with suffix ".DE" ("SAP.DE"). Empty if the provider supplies no assignment.
    symbols: tuple[str, ...] = ()


class SourceAdapter(ABC):
    @abstractmethod
    def metadata(self) -> AdapterMetadata: ...

    @abstractmethod
    def health(self) -> Health: ...

    disabled_reason = "API key not set"

    def is_configured(self) -> bool:
        """False if a required API key is missing. Then status 'disabled' with disabled_reason."""
        return True


class PriceAdapter(SourceAdapter):
    supported_exchanges: tuple[str, ...] = ()

    @abstractmethod
    def fetch_bars(
        self, symbol: str, exchange: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[BarRecord]: ...

    def fetch_quote(self, symbol: str, exchange: str) -> QuoteRecord | None:
        return None

    def search_instruments(self, query: str) -> list[InstrumentRecord]:
        return []


@dataclass(frozen=True)
class NewsTarget:
    """An observed instrument (from the watchlists). Adapters use symbol, name or ISIN depending on the provider."""

    symbol: str
    exchange: str
    name: str
    isin: str | None = None


class NewsAdapter(SourceAdapter):
    supported_exchanges: tuple[str, ...] = ("XNYS", "XNAS", "XETR")
    poll_seconds: int = 600  # retrieval interval in the worker
    # True: news without a proven instrument assignment is discarded (noisy sources like GDELT)
    require_match: bool = False

    @abstractmethod
    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]: ...

    def fetch_news_for(self, targets: list[NewsTarget], since: datetime) -> list[NewsRecord]:
        """Default: fetch by symbols of the supported exchanges. Adapters that need names or another
        symbol notation (GDELT, Marketaux) override this method."""
        symbols = [t.symbol for t in targets if t.exchange in self.supported_exchanges]
        return self.fetch_news(symbols, since) if symbols else []
