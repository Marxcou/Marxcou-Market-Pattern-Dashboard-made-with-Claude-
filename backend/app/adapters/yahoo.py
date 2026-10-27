"""Yahoo Finance (unofficial): daily data for US and XETRA via the public chart endpoint.

Active only with YAHOO_ENABLED=true in .env. There is no official API and no terms of use that explicitly
allow this use; the endpoint can change without notice. Therefore off by default and marked as
unofficial on the Sources page. If the endpoint returns something unexpected, there is a
SourceError, never estimated values (core rule 6)."""
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, BarRecord, PriceAdapter, Timeframe
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError
from app.config import get_settings

_SUFFIX = {"XNYS": "", "XNAS": "", "XETR": ".DE"}
# Without a browser-like user agent the endpoint usually answers with HTTP 429
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/128.0 Safari/537.36", "Accept": "application/json"}


def yahoo_symbol(symbol: str, exchange: str) -> str:
    return f"{symbol.upper().replace('.', '-')}{_SUFFIX[exchange]}"


class YahooAdapter(ProbedHealth, PriceAdapter):
    key = "yahoo"
    supported_exchanges = ("XNYS", "XNAS", "XETR")
    disabled_reason = "In .env ausgeschaltet (YAHOO_ENABLED=false)"

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self._enabled = get_settings().yahoo_enabled
        self.http = ResilientHttp(base_url="https://query1.finance.yahoo.com", headers=_HEADERS, rate_per_min=30,
                                  transport=transport, **kw)

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="Yahoo Finance (unofficial)", kind="price",
            description="Daily data (end of trading) for US stocks and XETRA via the public chart endpoint of "
                        "Yahoo Finance. Unofficial: no documented API, can change without notice. "
                        "Prices split-adjusted, not dividend-adjusted. No intraday data in this dashboard.",
            homepage="https://finance.yahoo.com", terms_url="https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
            update_interval="daily", delay_text="end of trading (daily data)", requires_key=False, is_official=False,
        )

    def is_configured(self) -> bool:
        return self._enabled

    def _chart(self, ticker: str, params: dict[str, Any]) -> dict[str, Any]:
        resp = self.http.request("GET", f"/v8/finance/chart/{ticker}", params=params)
        try:
            body = resp.json()
        except ValueError as exc:
            raise SourceError("Yahoo did not return JSON") from exc
        chart = body.get("chart") if isinstance(body, dict) else None
        if not isinstance(chart, dict):
            raise SourceError("Unexpected response format from Yahoo")
        if chart.get("error"):
            err = chart["error"]
            code = err.get("code") if isinstance(err, dict) else None
            if code == "Not Found":
                return {}
            raise SourceError(f"Yahoo reports an error: {code or 'unknown'}")
        results = chart.get("result") or []
        return results[0] if results and isinstance(results[0], dict) else {}

    def _probe(self) -> None:
        self._chart("AAPL", {"range": "5d", "interval": "1d"})

    def fetch_bars(
        self, symbol: str, exchange: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[BarRecord]:
        if timeframe != "1d" or exchange not in _SUFFIX:
            return []
        result = self._chart(yahoo_symbol(symbol, exchange), {
            "period1": int(start.timestamp()), "period2": int(end.timestamp()), "interval": "1d",
            "events": "div,split", "includePrePost": "false",
        })
        return parse_chart(result, symbol, exchange, datetime.now(UTC))


def _trading_day(ts: int, gmtoffset: int) -> date:
    """Yahoo stamps daily candles with the start of trading; the calendar day at the exchange is what counts."""
    return (datetime.fromtimestamp(ts, UTC) + timedelta(seconds=gmtoffset)).date()


def parse_chart(result: dict[str, Any], symbol: str, exchange: str, fetched_at: datetime) -> list[BarRecord]:
    """Daily candles with timestamp 00:00 UTC of the trading day (like Stooq). Days with missing values are
    left out instead of filled in."""
    if not result:
        return []
    try:
        stamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0] if stamps else {}
        offset = int((result.get("meta") or {}).get("gmtoffset") or 0)
        cols = [quote.get(k) or [] for k in ("open", "high", "low", "close", "volume")]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SourceError("Unexpected response format from Yahoo") from exc
    if any(len(c) != len(stamps) for c in cols[:4]):
        raise SourceError("Unexpected response format from Yahoo (column lengths differ)")
    out: dict[date, BarRecord] = {}
    for i, ts in enumerate(stamps):
        o, h, lo, c = (cols[k][i] for k in range(4))
        if o is None or h is None or lo is None or c is None:
            continue
        vol = cols[4][i] if i < len(cols[4]) else None
        day = _trading_day(int(ts), offset)
        out[day] = BarRecord(
            symbol=symbol, exchange=exchange, timeframe="1d",
            ts_utc=datetime(day.year, day.month, day.day, tzinfo=UTC), open=float(o), high=float(h), low=float(lo),
            close=float(c), volume=float(vol) if vol is not None else None, source_key="yahoo", fetched_at=fetched_at,
        )
    return [out[d] for d in sorted(out)]
