"""Triangles (ascending, descending, symmetrical) and wedges (rising, falling).

Candidates are 4 to 6 consecutive turning points. A least-squares line is fitted through the highs and
through the lows. The type follows from the slopes of the two lines (in % of the mean closing price per
candle)."""
import numpy as np

from app.analysis import fmt
from app.analysis.patterns.common import (
    Context,
    Criterion,
    Detection,
    Direction,
    KeyPoint,
    Line,
    all_required_pass,
    crit_ge,
    crit_le,
    deadline,
    finalize,
    score_ge,
    score_le,
    volume_ratio_criterion,
)
from app.analysis.pivots import Pivot

WEIGHTS = {"form": 0.25, "verengung": 0.20, "anpassung": 0.20, "beruehrungen": 0.15, "innerhalb": 0.10,
           "volumen": 0.10}

TYPES: dict[str, tuple[str, Direction]] = {
    "dreieck_aufsteigend": ("Ascending triangle", "aufwärts"),
    "dreieck_absteigend": ("Descending triangle", "abwärts"),
    "dreieck_symmetrisch": ("Symmetrical triangle", "offen"),
    "keil_steigend": ("Rising wedge", "abwärts"),
    "keil_fallend": ("Falling wedge", "aufwärts"),
}


def _fit(points: list[Pivot]) -> tuple[float, float, float]:
    """Line through the points: (slope per candle, intercept, largest deviation in %)."""
    x = np.array([p.idx for p in points], dtype=np.float64)
    y = np.array([p.price for p in points], dtype=np.float64)
    slope, intercept = np.polyfit(x, y, 1)
    dev = float(np.max(np.abs(y - (slope * x + intercept)) / y * 100))
    return float(slope), float(intercept), dev


def classify(s_up: float, s_lo: float, flat: float, min_slope: float) -> str | None:
    if abs(s_up) <= flat and s_lo >= min_slope:
        return "dreieck_aufsteigend"
    if abs(s_lo) <= flat and s_up <= -min_slope:
        return "dreieck_absteigend"
    if s_up <= -min_slope and s_lo >= min_slope:
        return "dreieck_symmetrisch"
    if s_up >= min_slope and s_lo >= min_slope and s_lo > s_up:
        return "keil_steigend"
    if s_up <= -min_slope and s_lo <= -min_slope and s_up < s_lo:
        return "keil_fallend"
    return None


def find_triangles(ctx: Context) -> list[Detection]:
    p = ctx.params["dreieck_keil"]
    out: list[Detection] = []
    pv = ctx.pivots
    for m in range(int(p["min_pivots"]), int(p["max_pivots"]) + 1):
        for k in range(0, len(pv) - m + 1):
            det = _candidate(ctx, pv[k : k + m])
            if det is not None:
                out.append(det)
    return out


def _candidate(ctx: Context, seq: list[Pivot]) -> Detection | None:
    p = ctx.params["dreieck_keil"]
    highs = [q for q in seq if q.kind == "H"]
    lows = [q for q in seq if q.kind == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return None
    start, end = seq[0].idx, seq[-1].idx
    width = end - start
    if not (p["min_breite_kerzen"] <= width <= p["max_breite_kerzen"]):
        return None
    close = ctx.bars.close
    ref = float(close[start : end + 1].mean())
    su, bu, dev_u = _fit(highs)
    sl, bl, dev_l = _fit(lows)
    s_up, s_lo = su / ref * 100, sl / ref * 100
    ptype = classify(s_up, s_lo, p["flach_steigung_pct"], p["min_steigung_pct"])
    if ptype is None:
        return None
    upper = Line("obere_linie", "Upper boundary", start, su * start + bu, end, su * end + bu)
    lower = Line("untere_linie", "Lower boundary", start, sl * start + bl, end, sl * end + bl)
    w0, w1 = upper.at(start) - lower.at(start), upper.at(end) - lower.at(end)
    if w0 <= 0 or w1 <= 0:
        return None
    name, direction = TYPES[ptype]
    crit: list[Criterion] = []

    flat, mn = p["flach_steigung_pct"], p["min_steigung_pct"]
    form_text = f"Slope of upper line {fmt.num(s_up, 3)}% per candle, lower line {fmt.num(s_lo, 3)}% per candle"
    if ptype == "dreieck_aufsteigend":
        rule = f"upper line horizontal (|slope| ≤ {fmt.num(flat)}%), lower line rises (≥ {fmt.num(mn)}%)"
        sub = (score_le(abs(s_up), 0, flat) + score_ge(s_lo, 3 * mn, mn)) / 2
    elif ptype == "dreieck_absteigend":
        rule = f"lower line horizontal (|slope| ≤ {fmt.num(flat)}%), upper line falls (≤ −{fmt.num(mn)}%)"
        sub = (score_le(abs(s_lo), 0, flat) + score_ge(-s_up, 3 * mn, mn)) / 2
    elif ptype == "dreieck_symmetrisch":
        rule = f"upper line falls and lower line rises, each by at least {fmt.num(mn)}% per candle"
        sub = (score_ge(-s_up, 3 * mn, mn) + score_ge(s_lo, 3 * mn, mn)) / 2
    elif ptype == "keil_steigend":
        rule = f"both lines rise (≥ {fmt.num(mn)}% per candle), the lower one more steeply"
        sub = (score_ge(min(s_up, s_lo), 3 * mn, mn) + 1.0) / 2
    else:
        rule = f"both lines fall (≤ −{fmt.num(mn)}% per candle), the upper one more steeply"
        sub = (score_ge(-max(s_up, s_lo), 3 * mn, mn) + 1.0) / 2
    crit.append(Criterion("form", "Course of the lines", rule, None, round(s_lo - s_up, 4), "% per candle",
                          form_text, True, True, round(sub, 4), WEIGHTS["form"]))

    narrowing = (1 - w1 / w0) * 100
    crit.append(crit_ge(
        "verengung", "Narrowing of the range",
        f"Range narrows by at least {fmt.pct(p['min_verengung_pct'], 0)}", narrowing, p["min_verengung_pct"],
        p["ideal_verengung_pct"], "%",
        f"Range on {ctx.date(start)}: {fmt.price(w0)}, on {ctx.date(end)}: {fmt.price(w1)}, "
        f"narrowing {fmt.pct(narrowing, 1)}", WEIGHTS["verengung"]))

    dev = max(dev_u, dev_l)
    crit.append(crit_le(
        "anpassung", "Position of the turning points on the lines",
        f"every turning point at most {fmt.pct(p['max_anpassung_pct'], 1)} away from its line",
        dev, p["max_anpassung_pct"], 0.0, "%",
        f"largest deviation {fmt.pct(dev)} ({len(highs)} highs, {len(lows)} lows)", WEIGHTS["anpassung"]))

    touches = min(len(highs), len(lows))
    crit.append(crit_ge(
        "beruehrungen", "Touches per line", "at least 2 turning points on each line", float(touches), 2.0, 3.0,
        "count", f"{len(highs)} touches on top, {len(lows)} on the bottom", WEIGHTS["beruehrungen"]))

    tol = p["toleranz_atr"] * ctx.atr[start : end + 1]
    idx = np.arange(start, end + 1)
    up_v = su * idx + bu
    lo_v = sl * idx + bl
    c = close[start : end + 1]
    inside = float(np.mean((c <= up_v + tol) & (c >= lo_v - tol)) * 100)
    crit.append(crit_ge(
        "innerhalb", "Closing prices between the lines",
        f"at least {fmt.pct(p['min_anteil_innerhalb_pct'], 0)} of the closing prices between the lines "
        f"(tolerance {fmt.num(p['toleranz_atr'], 1)} ATR)", inside, p["min_anteil_innerhalb_pct"], 100.0, "%",
        f"{fmt.pct(inside, 0)} of {end - start + 1} closing prices inside", WEIGHTS["innerhalb"]))

    half = start + width // 2
    vol = volume_ratio_criterion(
        ctx, "volumen", "Volume trend", "Volume in the second half lower than in the first "
        "(quality criterion)", (half + 1, end), (start, half), "second half", "first half", WEIGHTS["volumen"])
    if vol is not None:
        crit.append(vol)

    if not all_required_pass(crit):
        return None

    apex: int | None = None
    if su != sl:
        x = (bl - bu) / (su - sl)
        if x > end:
            apex = int(np.ceil(x))
    if direction == "abwärts":
        confirmation, invalidation = lower, upper
        conf_rule, inv_rule = "the lower boundary", "the upper boundary"
    else:
        confirmation, invalidation = upper, lower
        conf_rule, inv_rule = "the upper boundary", "the lower boundary"
    kps = [KeyPoint(f"beruehrung_oben_{i + 1}", f"Touch on top {i + 1}", q.idx, q.price) for i, q in enumerate(highs)]
    kps += [KeyPoint(f"beruehrung_unten_{i + 1}", f"Touch on bottom {i + 1}", q.idx, q.price)
            for i, q in enumerate(lows)]
    det = Detection(
        pattern_type=ptype, name=name, direction=direction, start_idx=start, end_idx=end,
        formed_idx=max(q.confirmed_idx for q in seq), key_points=sorted(kps, key=lambda k: k.idx),
        lines=[upper, lower], criteria=crit, confirmation=confirmation, invalidation=invalidation,
        deadline_idx=deadline(ctx, start, end), apex_idx=apex, family="dreieck_keil",
    )
    return finalize(ctx, det, conf_rule, inv_rule)
