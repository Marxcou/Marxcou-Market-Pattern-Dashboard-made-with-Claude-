"""Head and shoulders formation (and inverse) from five consecutive turning points:
shoulder, neck 1, head, neck 2, shoulder. The neckline connects the two neck points."""
import math

from app.analysis import fmt
from app.analysis.patterns.common import (
    Context,
    Criterion,
    Detection,
    KeyPoint,
    Line,
    all_required_pass,
    around,
    crit_ge,
    crit_le,
    deadline,
    finalize,
    pct_diff,
    volume_ratio_criterion,
)

WEIGHTS = {"kopf_ueberhang": 0.25, "schulter_abweichung": 0.25, "nacken_neigung": 0.15, "zeit_symmetrie": 0.15,
           "vortrend": 0.10, "volumen": 0.10}


def find_head_shoulders(ctx: Context) -> list[Detection]:
    out: list[Detection] = []
    pv = ctx.pivots
    for k in range(1, len(pv) - 4):
        seq = pv[k : k + 5]
        # normal: H L H L H (head on top); inverse: L H L H L
        inverse = seq[0].kind == "L"
        det = _candidate(ctx, pv[k - 1].price, [(s.idx, s.price) for s in seq], inverse, seq[-1].confirmed_idx)
        if det is not None:
            out.append(det)
    return out


def _candidate(ctx: Context, prev_price: float, pts: list[tuple[int, float]], inverse: bool,
               formed_idx: int) -> Detection | None:
    p = ctx.params["kopf_schulter"]
    (ils, pls), (in1, pn1), (ih, ph), (in2, pn2), (irs, prs) = pts
    width = irs - ils
    if not (p["min_breite_kerzen"] <= width <= p["max_breite_kerzen"]):
        return None
    sgn = -1.0 if inverse else 1.0  # inverse: mirror values so the same rules apply
    crit: list[Criterion] = []

    outer_shoulder = min(pls, prs) if inverse else max(pls, prs)
    overhang = sgn * (ph - outer_shoulder) / abs(outer_shoulder) * 100
    over = "below" if inverse else "above"
    crit.append(crit_ge(
        "kopf_ueberhang", "Head relative to the shoulders",
        f"Head is at least {fmt.pct(p['min_kopf_ueberhang_pct'], 1)} {over} the "
        f"{'lower' if inverse else 'higher'} shoulder",
        overhang, p["min_kopf_ueberhang_pct"], p["ideal_kopf_ueberhang_pct"], "%",
        f"Head: {fmt.price(ph)} on {ctx.date(ih)}, {fmt.pct(overhang)} {over} the shoulder at "
        f"{fmt.price(outer_shoulder)}", WEIGHTS["kopf_ueberhang"]))

    sdev = pct_diff(pls, prs)
    crit.append(crit_le(
        "schulter_abweichung", "Symmetry of the shoulders",
        f"Shoulders deviate by at most {fmt.pct(p['max_schulter_abweichung_pct'], 1)} from each other",
        sdev, p["max_schulter_abweichung_pct"], 0.0, "%",
        f"Left shoulder: {fmt.price(pls)} on {ctx.date(ils)}, right shoulder: {fmt.price(prs)} on "
        f"{ctx.date(irs)}, deviation {fmt.pct(sdev)}", WEIGHTS["schulter_abweichung"]))

    ndev = pct_diff(pn1, pn2)
    crit.append(crit_le(
        "nacken_neigung", "Slope of the neckline",
        f"Neck points deviate by at most {fmt.pct(p['max_nacken_neigung_pct'], 1)} from each other",
        ndev, p["max_nacken_neigung_pct"], 0.0, "%",
        f"Neck 1: {fmt.price(pn1)} on {ctx.date(in1)}, neck 2: {fmt.price(pn2)} on {ctx.date(in2)}, "
        f"difference {fmt.pct(ndev)}", WEIGHTS["nacken_neigung"]))

    left, right = ih - ils, irs - ih
    ratio = left / right if right else math.inf
    lo, hi = p["min_zeit_verhaeltnis"], p["max_zeit_verhaeltnis"]
    ok = lo <= ratio <= hi
    sub = max(0.0, 1 - abs(math.log(ratio)) / math.log(hi)) if ok and ratio > 0 else 0.0
    crit.append(Criterion(
        "zeit_symmetrie", "Time symmetry",
        f"Duration left shoulder to head / head to right shoulder between {fmt.num(lo, 1)} and {fmt.num(hi, 1)}",
        hi, round(ratio, 4) if math.isfinite(ratio) else None, "factor",
        f"{left} candles on the left, {right} candles on the right, "
        f"ratio {fmt.num(ratio) if math.isfinite(ratio) else '–'}",
        True, ok, round(sub, 4), WEIGHTS["zeit_symmetrie"]))

    prior = sgn * (pls - prev_price) / prev_price * 100
    crit.append(crit_ge(
        "vortrend", "Prior decline" if inverse else "Prior advance",
        f"Move from the previous turning point to the left shoulder of at least {fmt.pct(p['min_vortrend_pct'], 1)}",
        prior, p["min_vortrend_pct"], p["ideal_vortrend_pct"], "%",
        f"{'Decline' if inverse else 'Advance'} from {fmt.price(prev_price)} to {fmt.price(pls)} ({fmt.pct(prior)})",
        WEIGHTS["vortrend"]))

    vol = volume_ratio_criterion(
        ctx, "volumen", "Volume at the right shoulder",
        "Volume around the right shoulder lower than around the head (quality criterion)",
        around(ctx, irs), around(ctx, ih), "around the right shoulder", "around the head", WEIGHTS["volumen"])
    if vol is not None:
        crit.append(vol)

    if not all_required_pass(crit):
        return None
    # The neckline must lie between head and shoulders
    neck = Line("nackenlinie", "Neckline", in1, pn1, in2, pn2)
    if (max(pls, prs) >= min(pn1, pn2)) if inverse else (min(pls, prs) <= max(pn1, pn2)):
        return None

    buf = ctx.params["status"]["invalidierung_puffer_pct"] / 100
    inv_price = prs * (1 - buf) if inverse else prs * (1 + buf)
    det = Detection(
        pattern_type="kopf_schulter_invers" if inverse else "kopf_schulter",
        name="Inverse head and shoulders" if inverse else "Head and shoulders",
        direction="aufwärts" if inverse else "abwärts",
        start_idx=ils, end_idx=irs, formed_idx=formed_idx,
        key_points=[
            KeyPoint("linke_schulter", "Left shoulder", ils, pls),
            KeyPoint("nacken_1", "Neck 1", in1, pn1),
            KeyPoint("kopf", "Head", ih, ph),
            KeyPoint("nacken_2", "Neck 2", in2, pn2),
            KeyPoint("rechte_schulter", "Right shoulder", irs, prs),
        ],
        lines=[neck],
        criteria=crit,
        confirmation=neck,
        invalidation=Line.horizontal("ungueltigkeit", "Invalidation level", ils, irs, inv_price),
        deadline_idx=deadline(ctx, ils, irs),
        family="kopf_schulter_invers" if inverse else "kopf_schulter",
    )
    sign = "minus" if inverse else "plus"
    return finalize(ctx, det, "the neckline",
                    f"the invalidation level (right shoulder {sign} {fmt.pct(buf * 100, 1)})")
