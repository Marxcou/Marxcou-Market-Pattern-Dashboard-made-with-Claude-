"""Double bottom and double top from three consecutive turning points (extreme, intermediate point, extreme)."""
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
    score_band,
    volume_ratio_criterion,
)

WEIGHTS = {"extrem_abweichung": 0.35, "tiefe": 0.25, "abstand": 0.15, "vortrend": 0.15, "volumen": 0.10}


def find_double(ctx: Context) -> list[Detection]:
    out: list[Detection] = []
    pv = ctx.pivots
    for k in range(1, len(pv) - 2):
        prev, a, mid, b = pv[k - 1], pv[k], pv[k + 1], pv[k + 2]
        if a.kind != b.kind:
            continue
        det = _candidate(ctx, prev.price, a.idx, a.price, mid.idx, mid.price, b.idx, b.price, bottom=a.kind == "L",
                         formed_idx=b.confirmed_idx)
        if det is not None:
            out.append(det)
    return out


def _candidate(ctx: Context, prev_price: float, i1: int, p1: float, im: int, pm: float, i2: int, p2: float,
               bottom: bool, formed_idx: int) -> Detection | None:
    p = ctx.params["doppel"]
    ext = "Low" if bottom else "High"
    ext_key = "tief" if bottom else "hoch"
    mid_name = "Intermediate high" if bottom else "Intermediate low"
    crit: list[Criterion] = []

    dev = pct_diff(p1, p2)
    crit.append(crit_le(
        "extrem_abweichung", f"Deviation between the two {ext.lower()}s",
        f"The {ext.lower()}s deviate by at most {fmt.pct(p['max_extrem_abweichung_pct'], 1)} from each other",
        dev, p["max_extrem_abweichung_pct"], 0.0, "%",
        f"{ext} 1: {fmt.price(p1)} on {ctx.date(i1)}, {ext} 2: {fmt.price(p2)} on {ctx.date(i2)}, "
        f"deviation {fmt.pct(dev)}", WEIGHTS["extrem_abweichung"]))

    nearer = max(p1, p2) if bottom else min(p1, p2)
    depth = abs(pm - nearer) / nearer * 100
    crit.append(crit_ge(
        "tiefe", f"Depth of the {mid_name.lower()}", f"{mid_name} is at least {fmt.pct(p['min_tiefe_pct'], 1)} "
        f"{'above' if bottom else 'below'} the nearer {ext.lower()}",
        depth, p["min_tiefe_pct"], p["ideal_tiefe_pct"], "%",
        f"{mid_name} at {fmt.price(pm)} on {ctx.date(im)}, {fmt.pct(depth)} from the nearer {ext.lower()}",
        WEIGHTS["tiefe"]))

    sep = i2 - i1
    passed = p["min_abstand_kerzen"] <= sep <= p["max_abstand_kerzen"]
    crit.append(Criterion(
        "abstand", f"Distance between the two {ext.lower()}s",
        f"between {int(p['min_abstand_kerzen'])} and {int(p['max_abstand_kerzen'])} candles", p["min_abstand_kerzen"],
        float(sep), "candles", f"{sep} candles between {ext.lower()} 1 and {ext.lower()} 2", True, passed,
        score_band(sep, p["ideal_abstand_min"], p["ideal_abstand_max"], p["min_abstand_kerzen"],
                   p["max_abstand_kerzen"]) if passed else 0.0, WEIGHTS["abstand"]))

    prior = (prev_price - p1) / prev_price * 100 if bottom else (p1 - prev_price) / prev_price * 100
    crit.append(crit_ge(
        "vortrend", "Prior decline" if bottom else "Prior advance",
        f"Move from the previous turning point to {ext.lower()} 1 of at least {fmt.pct(p['min_vortrend_pct'], 1)}",
        prior, p["min_vortrend_pct"], p["ideal_vortrend_pct"], "%",
        f"{'Decline' if bottom else 'Advance'} from {fmt.price(prev_price)} to {fmt.price(p1)} "
        f"({fmt.pct(prior)})", WEIGHTS["vortrend"]))

    vol = volume_ratio_criterion(
        ctx, "volumen", f"Volume at the second {ext.lower()}",
        f"Volume around {ext.lower()} 2 lower than around {ext.lower()} 1 (quality criterion)",
        around(ctx, i2), around(ctx, i1), f"around {ext.lower()} 2", f"around {ext.lower()} 1", WEIGHTS["volumen"])
    if vol is not None:
        crit.append(vol)

    if not all_required_pass(crit):
        return None

    buf = ctx.params["status"]["invalidierung_puffer_pct"] / 100
    extreme = min(p1, p2) if bottom else max(p1, p2)
    inv_price = extreme * (1 - buf) if bottom else extreme * (1 + buf)
    neck = Line.horizontal("nackenlinie", "Neckline", i1, i2, pm)
    det = Detection(
        pattern_type="doppelboden" if bottom else "doppelhoch",
        name="Double bottom" if bottom else "Double top",
        direction="aufwärts" if bottom else "abwärts",
        start_idx=i1, end_idx=i2, formed_idx=formed_idx,
        key_points=[
            KeyPoint(f"{ext_key}_1", f"{ext} 1", i1, p1),
            KeyPoint("zwischenhoch" if bottom else "zwischentief", mid_name, im, pm),
            KeyPoint(f"{ext_key}_2", f"{ext} 2", i2, p2),
        ],
        lines=[neck],
        criteria=crit,
        confirmation=neck,
        invalidation=Line.horizontal("ungueltigkeit", "Invalidation level", i1, i2, inv_price),
        deadline_idx=deadline(ctx, i1, i2),
        family="doppelboden" if bottom else "doppelhoch",
    )
    side = "lower" if bottom else "higher"
    sign = "minus" if bottom else "plus"
    return finalize(ctx, det, "the neckline",
                    f"the invalidation level ({side} {ext.lower()} {sign} {fmt.pct(buf * 100, 1)})")
