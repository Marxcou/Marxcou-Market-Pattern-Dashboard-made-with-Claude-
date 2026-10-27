"""Flags and pennants: a steep move (flagpole) followed by a short consolidation.

Flagpole end i: highest high (or lowest low) of the last `max_stange_kerzen` candles that is not exceeded
during the consolidation. Start: lowest low (highest high) before it. A regression line is fitted through
the highs and through the lows of the consolidation. The longest consolidation is chosen that meets all
required criteria and whose last closing price lies inside the channel."""
import numpy as np

from app.analysis import fmt
from app.analysis.patterns.common import (
    Context,
    Criterion,
    Detection,
    KeyPoint,
    Line,
    all_required_pass,
    crit_ge,
    crit_le,
    finalize,
    volume_ratio_criterion,
)

WEIGHTS = {"stange": 0.25, "ruecksetzer": 0.15, "neigung": 0.15, "form": 0.15, "innerhalb": 0.10, "dauer": 0.10,
           "volumen": 0.10}


def find_flags(ctx: Context) -> list[Detection]:
    out: list[Detection] = []
    for up in (True, False):
        for i in range(len(ctx.bars)):
            det = _best_for_pole_end(ctx, i, up)
            if det is not None:
                out.append(det)
    return out


def _best_for_pole_end(ctx: Context, i: int, up: bool) -> Detection | None:
    p = ctx.params["flagge"]
    hi, lo = ctx.bars.high, ctx.bars.low
    max_pole, min_pole = int(p["max_stange_kerzen"]), int(p["min_stange_kerzen"])
    if i < min_pole:
        return None
    lookback = slice(max(0, i - max_pole), i + 1)
    if up and hi[i] < hi[lookback].max():
        return None
    if not up and lo[i] > lo[lookback].min():
        return None
    seg = slice(max(0, i - max_pole), i - min_pole + 1)
    if seg.stop <= seg.start:
        return None
    if up:
        j = seg.stop - 1 - int(np.argmin(lo[seg][::-1]))  # on a tie the latest point
        pole_start, pole_end = float(lo[j]), float(hi[i])
        pole_pct = (pole_end - pole_start) / pole_start * 100
    else:
        j = seg.stop - 1 - int(np.argmax(hi[seg][::-1]))
        pole_start, pole_end = float(hi[j]), float(lo[i])
        pole_pct = (pole_start - pole_end) / pole_start * 100
    if pole_pct < p["min_stange_pct"]:
        return None
    n = len(ctx.bars)
    for length in range(int(p["max_flagge_kerzen"]), int(p["min_flagge_kerzen"]) - 1, -1):
        end = i + length
        if end >= n:
            continue
        det = _candidate(ctx, j, i, end, up, pole_start, pole_end, pole_pct)
        if det is not None:
            return det
    return None


def _candidate(ctx: Context, j: int, i: int, end: int, up: bool, pole_start: float, pole_end: float,
               pole_pct: float) -> Detection | None:
    p = ctx.params["flagge"]
    hi, lo, close = ctx.bars.high, ctx.bars.low, ctx.bars.close
    w = slice(i + 1, end + 1)
    # The consolidation must not exceed the end of the flagpole
    if (up and hi[w].max() > pole_end) or (not up and lo[w].min() < pole_end):
        return None
    x = np.arange(i + 1, end + 1, dtype=np.float64)
    su, bu = (float(v) for v in np.polyfit(x, hi[w], 1))
    sl, bl = (float(v) for v in np.polyfit(x, lo[w], 1))
    ref = float(close[w].mean())
    s_up, s_lo = su / ref * 100, sl / ref * 100
    upper = Line("obere_linie", "Upper channel line", i + 1, su * (i + 1) + bu, end, su * end + bu)
    lower = Line("untere_linie", "Lower channel line", i + 1, sl * (i + 1) + bl, end, sl * end + bl)
    if upper.at(end) <= lower.at(end):
        return None

    wm = p["wimpel_min_steigung_pct"]
    pennant = s_up <= -wm and s_lo >= wm
    mid = (s_up + s_lo) / 2
    against = -mid if up else mid  # > 0: consolidation runs against the direction of the flagpole
    parallel = abs(s_up - s_lo)
    if not pennant:
        if parallel > p["max_parallel_abweichung_pct"] or against < -p["max_gegen_steigung_pct"]:
            return None

    crit: list[Criterion] = []
    word = "Advance" if up else "Decline"
    crit.append(crit_ge(
        "stange", "Flagpole", f"{word} of at least {fmt.pct(p['min_stange_pct'], 0)} within "
        f"{int(p['min_stange_kerzen'])} to {int(p['max_stange_kerzen'])} candles", pole_pct, p["min_stange_pct"],
        p["ideal_stange_pct"], "%",
        f"{word} from {fmt.price(pole_start)} on {ctx.date(j)} to {fmt.price(pole_end)} on {ctx.date(i)} "
        f"({fmt.pct(pole_pct, 1)} in {i - j} candles)", WEIGHTS["stange"]))

    pole_h = abs(pole_end - pole_start)
    extreme = float(lo[w].min()) if up else float(hi[w].max())
    retrace = abs(pole_end - extreme) / pole_h * 100
    crit.append(crit_le(
        "ruecksetzer", "Retracement within the consolidation",
        f"at most {fmt.pct(p['max_ruecksetzer_pct'], 0)} of the flagpole", retrace, p["max_ruecksetzer_pct"],
        p["ideal_ruecksetzer_pct"], "%",
        f"{'Lowest' if up else 'Highest'} price of the consolidation {fmt.price(extreme)}, "
        f"{fmt.pct(retrace, 1)} of the flagpole", WEIGHTS["ruecksetzer"]))

    pole_slope = pole_pct / (i - j)
    tilt = abs(mid) / pole_slope * 100
    crit.append(crit_le(
        "neigung", "Slope of the consolidation",
        f"Channel midline at most {fmt.pct(p['max_neigung_anteil_pct'], 0)} as steep as the flagpole",
        tilt, p["max_neigung_anteil_pct"], p["max_neigung_anteil_pct"] / 4, "%",
        f"Channel midline {fmt.num(mid, 3)}% per candle, flagpole {fmt.num(pole_slope, 3)}% per candle "
        f"({fmt.pct(tilt, 0)})", WEIGHTS["neigung"]))

    slopes = f"Slope on top {fmt.num(s_up, 3)}%, on the bottom {fmt.num(s_lo, 3)}% per candle"
    if pennant:
        crit.append(crit_ge(
            "form", "Converging lines (pennant)",
            f"upper line falls and lower line rises, each by at least {fmt.num(wm)}% per candle",
            min(-s_up, s_lo), wm, 3 * wm, "% per candle", slopes, WEIGHTS["form"]))
    else:
        crit.append(crit_le(
            "form", "Parallel lines (flag)",
            f"Slopes differ by at most {fmt.num(p['max_parallel_abweichung_pct'])}% per candle, "
            "channel runs horizontally or against the flagpole", parallel, p["max_parallel_abweichung_pct"], 0.0,
            "% per candle", slopes + f", difference {fmt.num(parallel, 3)}", WEIGHTS["form"]))

    tol = p["toleranz_atr"] * ctx.atr[w]
    c = close[w]
    inside_mask = (c <= su * x + bu + tol) & (c >= sl * x + bl - tol)
    if not bool(inside_mask[-1]):
        return None
    inside = float(inside_mask.mean() * 100)
    crit.append(crit_ge(
        "innerhalb", "Closing prices inside the channel",
        f"at least {fmt.pct(p['min_anteil_innerhalb_pct'], 0)} of the closing prices inside the channel "
        f"(tolerance {fmt.num(p['toleranz_atr'], 2)} ATR)", inside, p["min_anteil_innerhalb_pct"], 100.0, "%",
        f"{fmt.pct(inside, 0)} of {end - i} closing prices inside the channel", WEIGHTS["innerhalb"]))

    length = end - i
    crit.append(crit_le(
        "dauer", "Duration of the consolidation",
        f"{int(p['min_flagge_kerzen'])} to {int(p['max_flagge_kerzen'])} candles", float(length),
        p["max_flagge_kerzen"], p["min_flagge_kerzen"] * 2, "candles",
        f"{length} candles from {ctx.date(i + 1)} to {ctx.date(end)}", WEIGHTS["dauer"]))

    vol = volume_ratio_criterion(
        ctx, "volumen", "Volume during the consolidation",
        "Volume during the consolidation lower than in the flagpole (quality criterion)",
        (i + 1, end), (j, i), "during the consolidation", "in the flagpole", WEIGHTS["volumen"])
    if vol is not None:
        crit.append(vol)

    if not all_required_pass(crit):
        return None

    kind = "wimpel" if pennant else "flagge"
    ptype = f"{kind}_{'aufwaerts' if up else 'abwaerts'}"
    name = f"{'Pennant' if pennant else 'Flag'} after {'an advance' if up else 'a decline'}"
    inv = Line.horizontal("ungueltigkeit", "Invalidation level", i + 1, end, extreme)
    det = Detection(
        pattern_type=ptype, name=name, direction="aufwärts" if up else "abwärts", start_idx=j, end_idx=end,
        formed_idx=end,
        key_points=[
            KeyPoint("fahnenstange_start", "Start of flagpole", j, pole_start),
            KeyPoint("fahnenstange_ende", "End of flagpole", i, pole_end),
        ],
        lines=[upper, lower], criteria=crit,
        confirmation=upper if up else lower, invalidation=inv,
        deadline_idx=end + int(p["ausbruch_frist_kerzen"]), family=f"flagge_{'auf' if up else 'ab'}",
    )
    return finalize(ctx, det, f"the {'upper' if up else 'lower'} channel line",
                    f"the {'lowest' if up else 'highest'} price of the consolidation")
