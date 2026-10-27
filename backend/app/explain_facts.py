"""Explanation texts, part 1 (pure functions, no I/O): facts from the calculated values, deterministic template and
validation of an AI text. The AI text must not contain anything that is not in the facts (numbers and dates are
checked against the facts), no recommendation language and no links."""
import re
from datetime import datetime
from typing import Any

from app.analysis import fmt
from app.grundregeln import find_forbidden

MAX_CHARS = 2200
MIN_CHARS = 120
FREE_INTEGERS = 10  # number words like "two scenarios" may appear as digits
ADVICE = re.compile(r"recommend|advisable|advises?\b|get in\b|get out\b|entry point|exit point|investors should|"
                    r"you should|one should|empfehl|ratsam|einsteigen|aussteigen", re.IGNORECASE)
NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?\b")
DIRECTION_EN = {"aufwärts": "upward", "abwärts": "downward", "offen": "open"}
YES_NO = {True: "yes", False: "no"}


def _dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) and value else None


def _day(value: Any) -> str:
    ts = _dt(value)
    return fmt.day(ts) if ts else "unknown"


def _share(x: float | None, digits: int = 0) -> str:
    return "not available" if x is None else fmt.pct(x * 100, digits)


def level_labels(d: dict[str, Any]) -> tuple[str, str]:
    """Symmetrical triangle (direction "offen"): both levels are breakout levels, neither is an invalidation level."""
    if d["direction_if_confirmed"] == "offen":
        return "Upper breakout level", "Lower breakout level"
    return "Confirmation level", "Invalidation level"


def pattern_facts_text(d: dict[str, Any]) -> str:
    """All values of a detection as plain text, as they also appear in the interface."""
    conf = d["confidence"]
    lines = [
        f"Pattern: {d['name']} (timeframe {d['timeframe']})",
        f"Position in the chart: {_day(d['start_ts'])} to {_day(d['end_ts'])}",
        f"Status: {d['status_label']}. {d.get('status_reason') or ''}".strip(),
        f"Direction if confirmed: {DIRECTION_EN.get(d['direction_if_confirmed'], d['direction_if_confirmed'])}",
        "Key points:",
    ]
    lines += [f"- {k['label']}: {fmt.price(k['price'])} on {_day(k['ts'])}" for k in d["key_points"]]
    lines.append("Criteria (rule, actual value, met):")
    lines += [f"- {c['name']}: {c['rule']}; actual: {c['actual_text']}; met: {YES_NO[bool(c['passed'])]}"
              for c in d["criteria"]]
    lines.append(f"Detection confidence score: {fmt.pct(conf['score'] * 100, 0)}")
    lines.append(f"Calculation: {conf['method']}")
    lines += [f"- {b['name']}: sub-score {fmt.num(b['sub_score'], 2)}, weight {fmt.num(b['weight'], 2)}, "
              f"contribution {fmt.num(b['contribution'], 2)}" for b in conf["breakdown"]]
    conf_label, inv_label = level_labels(d)
    lines.append(f"{conf_label}: {fmt.price(d['confirmation_level'])}")
    lines.append(f"{inv_label}: {fmt.price(d['invalidation_level'])}")
    lines.append("Scenarios:")
    for s in d["scenarios"]:
        hist = s.get("historical") or {}
        hist_text = ""
        if hist.get("share") is not None and hist.get("sample_size") is not None:
            hist_text = f"; historically in {_share(hist['share'])} of {hist['sample_size']} cases"
        lines.append(f"- {s['title']}: {s['trigger_rule']}{hist_text}")
    lines.append(_backtest_line(d["backtest"]))
    return "\n".join(lines)


def _backtest_line(b: dict[str, Any]) -> str:
    if b.get("status") != "berechnet" or b.get("hit_rate") is None:
        return "Historical hit rate: not calculated. No backtest is available."
    parts = [f"Historical hit rate: {_share(b['hit_rate'])} over {b['sample_size']} cases"]
    if b.get("ci_low") is not None and b.get("ci_high") is not None:
        parts.append(f"95% interval {_share(b['ci_low'])} to {_share(b['ci_high'])}")
    if b.get("base_rate") is not None:
        parts.append(f"Base rate over all trading days {_share(b['base_rate'])}")
    if b.get("horizon_bars") is not None and b.get("min_move_pct") is not None:
        parts.append(f"Hit = move of at least {fmt.num(b['min_move_pct'], 1)}% within "
                     f"{b['horizon_bars']} candles")
    if b.get("not_better_than_random"):
        parts.append("historically not better than chance")
    if b.get("sample_size") is not None and b["sample_size"] < 30:
        parts.append("small sample, low significance")
    return "; ".join(parts)


def pattern_template(d: dict[str, Any]) -> str:
    """Deterministic text without AI from the same values."""
    conf = d["confidence"]
    passed = [c for c in d["criteria"] if c.get("passed")]
    text = [f"{d['name']}: detected in the period {_day(d['start_ts'])} to {_day(d['end_ts'])}. "
            f"Status: {d['status_label']}."]
    if passed:
        text.append("The pattern was detected because the following criteria are met: "
                    + "; ".join(c["actual_text"] for c in passed) + ".")
    text.append(f"The detection confidence is {fmt.pct(conf['score'] * 100, 0)} (weighted mean of the "
                "sub-scores of all criteria, breakdown see below).")
    if d["direction_if_confirmed"] == "offen":
        text.append(f"Possible scenarios: a closing price above {fmt.price(d['confirmation_level'])} counts as a "
                    "breakout "
                    f"to the upside, a closing price below {fmt.price(d['invalidation_level'])} as a breakout to the "
                    "downside. Without a breakout by the apex of the lines or the deadline, the pattern counts as "
                    "invalid. Which scenario occurs is open.")
    else:
        text.append(f"Possible scenarios: a closing price at {fmt.price(d['confirmation_level'])} counts as the "
                    f"confirmation level, a closing price at {fmt.price(d['invalidation_level'])} as the "
                    "invalidation level. "
                    "Which scenario occurs is open.")
    b = d["backtest"]
    if b.get("status") == "berechnet" and b.get("hit_rate") is not None:
        text.append(f"Historically, this pattern was followed in {_share(b['hit_rate'])} of {b['sample_size']} cases "
                    "by the move defined in the backtest."
                    + (" This is historically not better than chance." if b.get("not_better_than_random") else ""))
    else:
        text.append("No historical hit rate is available; none is estimated.")
    text.append("This description is created automatically, may be incorrect and is not investment advice.")
    return " ".join(text)


def _quantile_rows(steps: list[dict[str, Any]], currency: str | None) -> list[str]:
    rows: list[str] = []
    if not steps:
        return rows
    for idx in sorted({len(steps) // 2 - 1, len(steps) - 1}):
        if idx < 0:
            continue
        s, q = steps[idx], steps[idx]["quantiles"]
        rows.append(f"- Day {s.get('step', idx + 1)} ({_day(s['ts'])}): 95% range {fmt.price(q['2.5'], currency)} "
                    f"to {fmt.price(q['97.5'], currency)}, 80% range {fmt.price(q['10'], currency)} to "
                    f"{fmt.price(q['90'], currency)}, 50% range {fmt.price(q['25'], currency)} to "
                    f"{fmt.price(q['75'], currency)}, middle (median) {fmt.price(q['50'], currency)}")
    return rows


def forecast_facts_text(f: dict[str, Any], symbol: str) -> str:
    cur = f.get("currency")
    m = f.get("method") or {}
    lines = [
        f"Instrument: {symbol}",
        f"Method: {m.get('name', 'unknown')}: {m.get('description', '')}".strip(),
        f"Last closing price: {fmt.price(f['last_close'], cur)}, price data until {_day(f['based_on_until'])}",
        f"Horizon: {f['horizon_bars']} trading days",
        "Forecast corridor (probability ranges, not a single forecast):",
    ]
    lines += _quantile_rows(f["steps"], cur)
    if f.get("is_demo"):
        lines.append("Note: sample data (demo mode).")
    for p in f.get("pattern_scenarios") or []:
        lines.append(f"Pattern {p['name']} (scenarios from the model):")
        for s in p["scenarios"]:
            lines.append(f"- {s['title']} at {fmt.price(s['trigger_level'])}: {s['model_probability_text']}"
                         if s.get("trigger_level") is not None else f"- {s['title']}")
    lines.append(_forecast_backtest_line(f.get("backtest") or {}))
    for c in f.get("comparison") or []:
        lines.append(f"Comparison method: {c['name']}")
    return "\n".join(lines)


def _forecast_backtest_line(b: dict[str, Any]) -> str:
    if b.get("status") != "berechnet":
        return "Forecast quality (backtest): not calculated. How reliable the corridor was historically is unknown."
    parts = [f"Forecast quality in the backtest: {b['sample_size']} forecasts over {b['horizon_bars']} trading "
             "days each"]
    for c in b.get("coverage") or []:
        parts.append(f"nominal coverage {_share(c['nominal'])}, actual {_share(c['observed'], 1)}")
    if b.get("skill") is not None:
        parts.append(f"Skill versus the naive reference “price stays the same”: {fmt.num(b['skill'], 2)}")
    if b.get("verdict_text"):
        parts.append(b["verdict_text"])
    return "; ".join(parts)


def forecast_template(f: dict[str, Any], symbol: str) -> str:
    cur = f.get("currency")
    steps = f["steps"]
    last = steps[-1]
    q = last["quantiles"]
    text = [f"For {symbol}, the method {(f.get('method') or {}).get('name', 'unknown')} shows a corridor over "
            f"{f['horizon_bars']} trading days from the last closing price of {fmt.price(f['last_close'], cur)}.",
            f"At the end of the horizon the 50% range lies between {fmt.price(q['25'], cur)} and "
            f"{fmt.price(q['75'], cur)}, the 95% range between {fmt.price(q['2.5'], cur)} and "
            f"{fmt.price(q['97.5'], cur)}. These are probability ranges of the model, not a single forecast."]
    b = f.get("backtest") or {}
    if b.get("status") == "berechnet":
        text.append(f"The backtest over {b['sample_size']} forecasts checked how often the actual prices fell "
                    "within the bands; the results are shown under “Forecast quality”."
                    + (f" {b['verdict_text']}" if b.get("verdict_text") else ""))
    else:
        text.append("No backtest of the forecast quality is available; the reliability is therefore unknown.")
    text.append("This description is created automatically, may be incorrect and is not investment advice.")
    return " ".join(text)


def _value(token: str) -> float:
    return float(token.replace(",", ""))


def validate(text: str, facts_text: str) -> str | None:
    """None if the text is acceptable, otherwise the reason for rejection. Checked are length, recommendation language,
    links and that every number and every date comes from the facts."""
    if not MIN_CHARS <= len(text) <= MAX_CHARS:
        return "length outside the permitted range"
    if find_forbidden(text) or ADVICE.search(text):
        return "contains inadmissible language"
    if re.search(r"https?://|www\.", text):
        return "contains a link"
    facts_dates = {m.group(0)[:10] for m in DATE.finditer(facts_text)}
    for m in DATE.finditer(text):
        if m.group(0)[:10] not in facts_dates:
            return f"date {m.group(0)} is not in the facts"
    facts_numbers = {_value(m.group(0)) for m in NUMBER.finditer(DATE.sub(" ", facts_text))}
    for m in NUMBER.finditer(DATE.sub(" ", text)):
        v = _value(m.group(0))
        if v not in facts_numbers and not (float(v).is_integer() and 0 <= v <= FREE_INTEGERS):
            return f"number {m.group(0)} is not in the facts"
    return None
