"""Number and date formats (en) for the explanation texts (time zone Europe/Berlin)."""
from datetime import datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
CURRENCY = {"EUR": "€", "USD": "$"}


def num(x: float, digits: int = 2) -> str:
    return f"{x:,.{digits}f}"


def price(x: float, currency: str | None = None) -> str:
    """Price with currency sign; without a currency (pattern detection, instrument-neutral) just the number,
    with four decimals below 1."""
    if currency is None:
        return num(x, 4 if abs(x) < 1 else 2)
    return f"{CURRENCY.get(currency, currency)}{num(x)}"


def pct(x: float, digits: int = 2) -> str:
    return f"{num(x, digits)}%"


def day(ts: datetime) -> str:
    return ts.astimezone(BERLIN).strftime("%Y-%m-%d")


def stamp(ts: datetime, timeframe: str) -> str:
    return day(ts) if timeframe == "1d" else ts.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M")
