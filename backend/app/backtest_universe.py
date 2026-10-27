"""Fixed stock selection for the pattern backtest: DAX stocks (XETRA) and large US stocks (NYSE/Nasdaq).

These are current index members or currently large companies (survivorship bias, named in the result).
The DAX list reflects the composition to the best of our knowledge (as of 2025) and should be checked
before a run; `--universe-file` allows a custom list (one line per symbol:
`SYMBOL,EXCHANGE`, exchange = XETR, XNYS or XNAS). Symbols without data are listed as missing in the run."""
from pathlib import Path

DAX = [
    "ADS", "AIR", "ALV", "BAS", "BAYN", "BEI", "BMW", "BNR", "CBK", "CON", "DTG", "DBK", "DB1", "DHL", "DTE",
    "EOAN", "FRE", "HNR1", "HEI", "HEN3", "IFX", "MBG", "MRK", "MTX", "MUV2", "P911", "PAH3", "QIA", "RHM",
    "RWE", "SAP", "SRT3", "SIE", "ENR", "SHL", "SY1", "VOW3", "VNA", "ZAL", "1COV",
]

US_NASDAQ = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "COST", "NFLX", "PEP", "ADBE", "CSCO",
    "AMD", "INTC", "QCOM", "TXN", "AMGN", "INTU", "ISRG", "BKNG", "HON", "SBUX", "GILD", "MDLZ", "ADP",
    "REGN", "VRTX", "ADI", "LRCX", "MU", "AMAT", "KLAC", "PYPL", "MAR", "CSX", "ORLY", "MNST", "CTAS", "PANW",
]

US_NYSE = [
    "BRK-B", "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "MA", "PG", "HD", "CVX", "MRK", "ABBV", "KO", "LLY",
    "BAC", "PFE", "TMO", "CRM", "ACN", "MCD", "ABT", "DHR", "DIS", "WFC", "VZ", "NKE", "PM", "NEE", "LIN",
    "UNP", "RTX", "T", "LOW", "MS", "GS", "BA", "CAT", "IBM", "UPS", "SPGI", "DE", "GE", "BLK", "AXP", "C",
    "MMM", "LMT", "ORCL", "SCHW", "PLD", "MO", "CVS", "BMY", "MDT", "TGT", "SYK", "CB", "CI", "DUK",
]

UNIVERSE_LABEL = f"DAX selection ({len(DAX)} stocks) and {len(US_NASDAQ) + len(US_NYSE)} large US stocks"


def default_universe() -> list[tuple[str, str]]:
    return ([(s, "XETR") for s in DAX] + [(s, "XNAS") for s in US_NASDAQ] + [(s, "XNYS") for s in US_NYSE])


def read_universe_file(path: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        symbol, _, exchange = (p.strip() for p in line.partition(","))
        if exchange not in ("XETR", "XNYS", "XNAS"):
            raise ValueError(f"Unknown exchange in line '{raw}' (allowed: XETR, XNYS, XNAS)")
        out.append((symbol.upper(), exchange))
    return out
