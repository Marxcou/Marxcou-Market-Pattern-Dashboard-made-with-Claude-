"""Registry of all adapters. Workstreams 1B/2A/2B register their adapters here (one line per source).
As long as none is registered, the Sources page honestly shows an empty list."""
import logging
from datetime import UTC, datetime

from app.adapters.base import AdapterMetadata, Health, NewsAdapter, PriceAdapter, SourceAdapter

log = logging.getLogger(__name__)

_ADAPTERS: dict[str, SourceAdapter] = {}


def register(adapter: SourceAdapter) -> None:
    _ADAPTERS[adapter.metadata().key] = adapter


def all_adapters() -> list[SourceAdapter]:
    return list(_ADAPTERS.values())


def price_adapters() -> list[PriceAdapter]:
    return [a for a in _ADAPTERS.values() if isinstance(a, PriceAdapter)]


def news_adapters() -> list[NewsAdapter]:
    return [a for a in _ADAPTERS.values() if isinstance(a, NewsAdapter)]


def get_adapter(key: str) -> SourceAdapter | None:
    return _ADAPTERS.get(key)


def clear() -> None:  # tests only
    _ADAPTERS.clear()


class BrokenAdapter(SourceAdapter):
    """Placeholder for an adapter whose construction failed because of the configuration. It appears on the Sources
    page as 'disabled' with a reason (core rule 6: never disappear silently) and paralyzes nothing else."""

    def __init__(self, key: str, name: str, reason: str) -> None:
        self.key, self._name, self.disabled_reason = key, name, reason

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(key=self.key, name=self._name, kind="reference",
                               description="This source could not start because of a configuration error.",
                               homepage="", terms_url="", update_interval="not active", delay_text="not active",
                               requires_key=False)

    def health(self) -> Health:
        return Health(status="disabled", checked_at=datetime.now(UTC), message=self.disabled_reason)

    def is_configured(self) -> bool:
        return False


def _safe_build(build, key: str, name: str) -> SourceAdapter:  # type: ignore[no-untyped-def]
    try:
        return build()  # type: ignore[no-any-return]
    except Exception as exc:  # a configuration error must never prevent API and worker from starting
        log.warning("Adapter %s could not be started: %s: %s", key, type(exc).__name__, exc)
        return BrokenAdapter(key, name, f"Configuration error in .env ({type(exc).__name__}); source disabled")


def load_builtin_adapters() -> None:
    """Registers all built-in adapters. Adapters without an API key are registered anyway and shown as
    'disabled' on the Sources page (core rule 6: honest instead of silent)."""
    from app.adapters.alpaca import AlpacaAdapter
    from app.adapters.alphavantage_news import AlphaVantageNewsAdapter
    from app.adapters.finnhub import FinnhubAdapter
    from app.adapters.finnhub_news import FinnhubNewsAdapter
    from app.adapters.gdelt import GdeltAdapter
    from app.adapters.ir_feeds import IrFeedsAdapter
    from app.adapters.marketaux import MarketauxAdapter
    from app.adapters.openfigi import OpenFigiAdapter
    from app.adapters.rss import build_rss_adapters
    from app.adapters.sec_edgar import SecEdgarAdapter
    from app.adapters.stooq import StooqAdapter
    from app.adapters.yahoo import YahooAdapter
    from app.explain_service import ClaudeExplainSource
    from app.sentiment_claude import ClaudeSentimentSource
    from app.sentiment_lexicon import LexiconSentimentSource

    for adapter_cls in (
        AlpacaAdapter, FinnhubAdapter, StooqAdapter, YahooAdapter, OpenFigiAdapter, FinnhubNewsAdapter, SecEdgarAdapter,
        AlphaVantageNewsAdapter, MarketauxAdapter, GdeltAdapter, IrFeedsAdapter,
        LexiconSentimentSource, ClaudeSentimentSource, ClaudeExplainSource,
    ):
        if adapter_cls.key not in _ADAPTERS:
            register(_safe_build(adapter_cls, adapter_cls.key, adapter_cls.__name__))
    try:
        rss_adapters = build_rss_adapters()
    except Exception as exc:
        log.warning("RSS adapters could not be built: %s: %s", type(exc).__name__, exc)
        reason = f"Configuration error in .env ({type(exc).__name__}); source disabled"
        register(BrokenAdapter("rss", "RSS feeds", reason))
        rss_adapters = []
    for rss in rss_adapters:
        if rss.key not in _ADAPTERS:
            register(rss)
