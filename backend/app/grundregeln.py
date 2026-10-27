"""Core rule 1 (Grundregel 1): no recommendation language. This list is used by the CI test and at runtime
for AI texts. It is the only place in the code where the words appear."""
import re

DISCLAIMER = (
    "This dashboard does not constitute investment advice. All analyses are automated, "
    "may be incorrect and are for information only."
)

FORBIDDEN_TERMS = [
    # English (UI and analysis texts)
    "buy", "sell", "buy signal", "sell signal", "buy recommendation", "sell recommendation", "strong buy",
    "strong sell", "price target", "target price", "outperform", "underperform", "overweight", "underweight",
    # German (the UI can be switched to German)
    "kaufen", "verkaufen", "kaufsignal", "verkaufssignal", "kaufempfehlung", "verkaufsempfehlung", "kursziel",
    "übergewichten", "untergewichten",
]

_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in sorted(FORBIDDEN_TERMS, key=len, reverse=True)) + r")\b", re.IGNORECASE
)


def find_forbidden(text: str) -> list[str]:
    return sorted({m.group(1).lower() for m in _PATTERN.finditer(text)})
