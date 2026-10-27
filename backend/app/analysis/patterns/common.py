"""Shared building blocks of the patterns: data classes, sub-score functions, confidence, status, explanation text.

Confidence: weighted mean of the sub-scores (0 to 1) of all evaluated criteria. A sub-score is 1 at the
ideal value and falls linearly to 0 at the criterion's limit. If a value is missing (e.g. volume), the
criterion is not evaluated and the remaining weights are scaled up to sum to 1."""
import math
from dataclasses import dataclass, field
from typing import Literal

from app.analysis import fmt
from app.analysis.params import Params
from app.analysis.pivots import Pivot
from app.analysis.series import Bars, FloatArray, mean_volume

Direction = Literal["aufwärts", "abwärts", "offen"]
Status = Literal["in_bildung", "bestaetigt", "ungueltig"]

STATUS_LABELS: dict[str, str] = {"in_bildung": "Forming", "bestaetigt": "Confirmed", "ungueltig": "Invalid"}

CONFIDENCE_METHOD = (
    "Weighted mean of the sub-scores (0 to 1) of all criteria. A sub-score is 1 at the ideal value and "
    "falls linearly to 0 at the criterion's limit. Criteria that cannot be evaluated (e.g. missing volume) "
    "are dropped and the remaining weights are scaled up to sum to 1."
)


@dataclass(frozen=True)
class Context:
    bars: Bars
    atr: FloatArray
    pivots: list[Pivot]
    params: Params
    timeframe: str

    def date(self, idx: int) -> str:
        return fmt.stamp(self.bars.ts[idx], self.timeframe)


@dataclass(frozen=True)
class KeyPoint:
    role: str
    label: str
    idx: int
    price: float


@dataclass(frozen=True)
class Line:
    """Straight line through (i0, p0) and (i1, p1); horizontal if p0 == p1."""
    role: str
    label: str
    i0: int
    p0: float
    i1: int
    p1: float
    extend_right: bool = True

    @property
    def slope(self) -> float:
        return 0.0 if self.i1 == self.i0 else (self.p1 - self.p0) / (self.i1 - self.i0)

    def at(self, i: int) -> float:
        return self.p0 + self.slope * (i - self.i0)

    @classmethod
    def horizontal(cls, role: str, label: str, i0: int, i1: int, price: float) -> "Line":
        return cls(role, label, i0, price, i1, price)


@dataclass
class Criterion:
    key: str
    name: str
    rule: str
    threshold: float | None
    actual: float | None
    unit: str
    actual_text: str
    required: bool
    passed: bool
    sub_score: float
    weight: float


@dataclass
class Scenario:
    kind: str  # bestaetigung | scheitern | ausbruch_oben | ausbruch_unten
    title: str
    trigger_level: float
    trigger_rule: str
    description: str


@dataclass
class Detection:
    pattern_type: str
    name: str
    direction: Direction
    start_idx: int
    end_idx: int
    formed_idx: int  # last candle whose data enters the detection (for backtests without look-ahead)
    key_points: list[KeyPoint]
    lines: list[Line]
    criteria: list[Criterion]
    confirmation: Line
    invalidation: Line
    deadline_idx: int  # without confirmation up to here: invalid
    apex_idx: int | None = None  # triangles/wedges: apex reached without breakout = invalid
    # set by the status step
    status: Status = "in_bildung"
    status_reason: str = ""
    status_idx: int | None = None
    confirmed_idx: int | None = None
    invalidated_idx: int | None = None
    breakout_direction: Direction | None = None
    confirmation_level: float = 0.0
    invalidation_level: float = 0.0
    scenarios: list[Scenario] = field(default_factory=list)
    confidence: float = 0.0
    breakdown: list[dict[str, float | str]] = field(default_factory=list)
    explanation: str = ""
    family: str = ""


# ---------- Sub-scores ----------

def score_le(x: float, ideal: float, limit: float) -> float:
    """Smaller is better: 1 at x <= ideal, 0 at x >= limit, linear in between."""
    if x <= ideal:
        return 1.0
    if x >= limit or limit == ideal:
        return 0.0
    return round((limit - x) / (limit - ideal), 4)


def score_ge(x: float, ideal: float, limit: float) -> float:
    """Larger is better: 1 at x >= ideal, 0 at x <= limit, linear in between."""
    if x >= ideal:
        return 1.0
    if x <= limit or limit == ideal:
        return 0.0
    return round((x - limit) / (ideal - limit), 4)


def score_band(x: float, ideal_lo: float, ideal_hi: float, limit_lo: float, limit_hi: float) -> float:
    if x < ideal_lo:
        return score_ge(x, ideal_lo, limit_lo)
    if x > ideal_hi:
        return score_le(x, ideal_hi, limit_hi)
    return 1.0


def crit_le(key: str, name: str, rule: str, actual: float, threshold: float, ideal: float, unit: str,
            actual_text: str, weight: float, required: bool = True) -> Criterion:
    return Criterion(key, name, rule, threshold, round(actual, 4), unit, actual_text, required,
                     actual <= threshold, score_le(actual, ideal, threshold), weight)


def crit_ge(key: str, name: str, rule: str, actual: float, threshold: float, ideal: float, unit: str,
            actual_text: str, weight: float, required: bool = True) -> Criterion:
    return Criterion(key, name, rule, threshold, round(actual, 4), unit, actual_text, required,
                     actual >= threshold, score_ge(actual, ideal, threshold), weight)


def pct_diff(a: float, b: float) -> float:
    """Deviation in % relative to the smaller value."""
    return abs(a - b) / min(abs(a), abs(b)) * 100.0


def volume_ratio_criterion(ctx: Context, key: str, name: str, rule: str, later: tuple[int, int],
                           earlier: tuple[int, int], later_label: str, earlier_label: str,
                           weight: float) -> Criterion | None:
    """Quality criterion: volume in the later section lower than in the earlier one. None without volume data."""
    if not ctx.bars.has_volume:
        return None
    v_late = mean_volume(ctx.bars, *later)
    v_early = mean_volume(ctx.bars, *earlier)
    if not (math.isfinite(v_late) and math.isfinite(v_early)) or v_early <= 0:
        return None
    p = ctx.params["volumen"]
    ratio = v_late / v_early
    text = (f"Mean volume {later_label}: {fmt.num(v_late, 0)}, {earlier_label}: {fmt.num(v_early, 0)}, "
            f"ratio {fmt.num(ratio)}")
    return Criterion(key, name, rule, 1.0, round(ratio, 4), "factor", text, False, ratio < 1.0,
                     score_le(ratio, p["ideal_verhaeltnis"], p["grenz_verhaeltnis"]), weight)


def around(ctx: Context, idx: int) -> tuple[int, int]:
    w = int(ctx.params["volumen"]["fenster_kerzen"])
    return idx - w, idx + w


def all_required_pass(criteria: list[Criterion]) -> bool:
    return all(c.passed for c in criteria if c.required)


def deadline(ctx: Context, start: int, end: int) -> int:
    p = ctx.params["status"]
    width = end - start
    return end + int(min(max(width, p["frist_min_kerzen"]), p["frist_max_kerzen"]))


# ---------- Confidence, status, scenarios, text ----------

def apply_confidence(det: Detection) -> None:
    total = sum(c.weight for c in det.criteria)
    breakdown: list[dict[str, float | str]] = []
    score = 0.0
    for c in det.criteria:
        w = c.weight / total if total else 0.0
        contribution = w * c.sub_score
        score += contribution
        breakdown.append({"key": c.key, "name": c.name, "weight": round(w, 4), "sub_score": round(c.sub_score, 4),
                          "contribution": round(contribution, 4)})
    det.confidence = round(score, 4)
    det.breakdown = breakdown


def evaluate_status(ctx: Context, det: Detection) -> None:
    """Walks through the candles after the pattern end. The event that occurs first counts (by closing price).
    After a confirmation, `invalidated_idx` is still set if the price later crosses the invalidation level
    that applied at confirmation; the status then stays 'bestaetigt'."""
    close = ctx.bars.close
    n = len(ctx.bars)
    up = det.direction == "aufwärts"
    frozen_inv: float | None = None
    for t in range(det.end_idx + 1, n):
        c = float(close[t])
        if det.confirmed_idx is None:
            conf, inv = det.confirmation.at(t), det.invalidation.at(t)
            if det.direction == "offen":
                if c > conf:
                    det.confirmed_idx, det.breakout_direction = t, "aufwärts"
                elif c < inv:
                    det.confirmed_idx, det.breakout_direction = t, "abwärts"
            elif (up and c > conf) or (not up and c < conf):
                det.confirmed_idx = t
            elif (up and c < inv) or (not up and c > inv):
                det.invalidated_idx = t
                det.status, det.status_idx = "ungueltig", t
                det.status_reason = f"Closing price {fmt.price(c)} on {ctx.date(t)} beyond the invalidation level " \
                                    f"{fmt.price(inv)}"
                return
            if det.confirmed_idx is not None:
                det.status, det.status_idx = "bestaetigt", t
                lvl = conf if det.breakout_direction != "abwärts" else inv
                det.status_reason = f"Closing price {fmt.price(c)} on {ctx.date(t)} beyond the level {fmt.price(lvl)}"
                if det.direction == "offen":
                    frozen_inv = inv if det.breakout_direction == "aufwärts" else conf
                else:
                    frozen_inv = inv
                continue
            if det.apex_idx is not None and t >= det.apex_idx:
                det.status, det.status_idx, det.invalidated_idx = "ungueltig", t, t
                det.status_reason = f"Apex of the lines reached on {ctx.date(t)} without a breakout"
                return
            if t >= det.deadline_idx:
                det.status, det.status_idx, det.invalidated_idx = "ungueltig", t, t
                det.status_reason = f"No confirmation by the deadline on {ctx.date(t)}"
                return
        else:
            assert frozen_inv is not None
            falls_back = c < frozen_inv if (det.breakout_direction or det.direction) == "aufwärts" else c > frozen_inv
            if falls_back:
                det.invalidated_idx = t
                return
    if det.confirmed_idx is None:
        det.status_reason = ("Neither the confirmation level nor the invalidation level has been crossed by a "
                             "closing price so far")


def level_ref_idx(ctx: Context, det: Detection) -> int:
    """Candle at which sloped lines are evaluated for the scenario levels."""
    return det.status_idx if det.status_idx is not None else len(ctx.bars) - 1


def build_scenarios(ctx: Context, det: Detection, conf_rule: str, inv_rule: str) -> None:
    ref = level_ref_idx(ctx, det)
    conf, inv = det.confirmation.at(ref), det.invalidation.at(ref)
    det.confirmation_level, det.invalidation_level = round(conf, 4), round(inv, 4)
    when = "" if det.status_idx is None else f" (value on {ctx.date(ref)})"
    if det.direction == "offen":
        det.scenarios = [
            Scenario("ausbruch_oben", "Breakout upward", round(conf, 4),
                     f"Closing price above {conf_rule} at {fmt.price(conf)}{when}",
                     f"If the price closes above {fmt.price(conf)}, the “{det.name}” pattern "
                     "is considered resolved to the upside."),
            Scenario("ausbruch_unten", "Breakout downward", round(inv, 4),
                     f"Closing price below {inv_rule} at {fmt.price(inv)}{when}",
                     f"If the price closes below {fmt.price(inv)}, the “{det.name}” pattern "
                     "is considered resolved to the downside."),
        ]
        return
    over, under = ("above", "below") if det.direction == "aufwärts" else ("below", "above")
    det.scenarios = [
        Scenario("bestaetigung", "Confirmation", round(conf, 4),
                 f"Closing price {over} {conf_rule} at {fmt.price(conf)}{when}",
                 f"If the price closes {over} {fmt.price(conf)}, the “{det.name}” pattern is considered confirmed. "
                 "The backtest shows how things went historically afterwards."),
        Scenario("scheitern", "Failure", round(inv, 4),
                 f"Closing price {under} {inv_rule} at {fmt.price(inv)}{when}",
                 f"If the price closes {under} {fmt.price(inv)} before the confirmation level is reached, "
                 "the pattern is considered invalid."),
    ]


def build_explanation(ctx: Context, det: Detection) -> None:
    parts = [f"{det.name} from {ctx.date(det.start_idx)} to {ctx.date(det.end_idx)}."]
    parts += [c.actual_text + "." for c in det.criteria if c.required]
    parts.append(f"Detection confidence: {fmt.pct(det.confidence * 100, 0)} "
                 "(weighted mean of the sub-scores, see breakdown).")
    parts.append(f"Status: {STATUS_LABELS[det.status]}. {det.status_reason}.")
    parts += [f"{s.title}: {s.trigger_rule}." for s in det.scenarios]
    det.explanation = " ".join(parts)


def finalize(ctx: Context, det: Detection, conf_rule: str, inv_rule: str) -> Detection:
    apply_confidence(det)
    evaluate_status(ctx, det)
    build_scenarios(ctx, det, conf_rule, inv_rule)
    build_explanation(ctx, det)
    return det


def dedupe(dets: list[Detection]) -> list[Detection]:
    """If two detections of the same family overlap by at least half of the shorter one, the one with the
    higher confidence is kept (on a tie the longer one, then the earlier one)."""
    ranked = sorted(dets, key=lambda d: (-d.confidence, -(d.end_idx - d.start_idx), d.start_idx, d.pattern_type))
    kept: list[Detection] = []
    for d in ranked:
        clash = False
        for k in kept:
            if k.family != d.family:
                continue
            overlap = min(k.end_idx, d.end_idx) - max(k.start_idx, d.start_idx)
            shorter = max(1, min(k.end_idx - k.start_idx, d.end_idx - d.start_idx))
            if overlap / shorter >= 0.5:
                clash = True
                break
        if not clash:
            kept.append(d)
    return sorted(kept, key=lambda d: (d.start_idx, d.pattern_type))
