"""Indicator events: golden/death cross, RSI divergence, Bollinger breakout, volume spike.
Rule-based and deterministic: same candles + same parameters = same events. Every event carries its
criteria with the actual values (duty to explain) and the parameters used.
The descriptions are neutral and contain no call to action (core rule 1)."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from app.analysis import indicators as ind
from app.analysis.fmt import num, price, stamp

ALGO_VERSION = "indicator-events-2"
F64 = np.ndarray

PARAMS: dict[str, dict[str, Any]] = {
    "cross": {"fast": 50, "slow": 200},
    "rsi_divergence": {"rsi_period": 14, "pivot_window": 5, "min_bars_apart": 5, "max_bars_apart": 60,
                       "min_price_diff_pct": 0.1, "min_rsi_diff": 2.0, "rsi_midline": 50.0},
    "bollinger": {"period": 20, "factor": 2.0},
    "volume_spike": {"lookback": 20, "min_z": 3.0, "min_ratio": 2.0},
}


@dataclass
class Series:
    """Completed candles in ascending time. volume is NaN if the source provides none."""
    ts: list[datetime]
    open: F64
    high: F64
    low: F64
    close: F64
    volume: F64
    timeframe: str
    currency: str

    def __len__(self) -> int:
        return len(self.ts)


@dataclass
class Event:
    type: str
    direction: str | None
    index: int  # candle of the marker
    confirmed_index: int  # candle from which the event was recognizable
    start_index: int
    title: str
    summary: str
    criteria: list[dict[str, Any]]
    values: dict[str, Any]
    params: dict[str, Any]
    ts: datetime = field(init=False)


def _crit(name: str, rule: str, required: str, actual: str, passed: bool = True) -> dict[str, Any]:
    return {"name": name, "rule": rule, "required": required, "actual": actual, "passed": passed}


def _f(x: float) -> float:
    return float(x)


def detect_crosses(s: Series) -> list[Event]:
    p = PARAMS["cross"]
    fast, slow = ind.sma(s.close, p["fast"]), ind.sma(s.close, p["slow"])
    out: list[Event] = []
    for i in range(1, len(s)):
        vals = (fast[i - 1], slow[i - 1], fast[i], slow[i])
        if any(np.isnan(v) for v in vals):
            continue
        f0, s0, f1, s1 = vals
        up = f0 <= s0 and f1 > s1
        down = f0 >= s0 and f1 < s1
        if not (up or down):
            continue
        fl, sl = f"SMA({p['fast']})", f"SMA({p['slow']})"
        cur = s.currency
        if up:
            typ, direction = "golden_cross", "up"
            title = f"Golden cross ({fl} above {sl})"
            crit = [
                _crit("Previous candle: fast average not above the slow one", f"{fl} ≤ {sl}",
                      f"≤ {price(s0, cur)}", price(f0, cur)),
                _crit("Candle: fast average above the slow one", f"{fl} > {sl}",
                      f"> {price(s1, cur)}", price(f1, cur)),
            ]
            summary = (f"On {stamp(s.ts[i], s.timeframe)} the {fl} rose to {price(f1, cur)} and was thus above the "
                       f"{sl} ({price(s1, cur)}); on the previous candle it was still at {price(f0, cur)} "
                       f"(≤ {price(s0, cur)}).")
        else:
            typ, direction = "death_cross", "down"
            title = f"Death cross ({fl} below {sl})"
            crit = [
                _crit("Previous candle: fast average not below the slow one", f"{fl} ≥ {sl}",
                      f"≥ {price(s0, cur)}", price(f0, cur)),
                _crit("Candle: fast average below the slow one", f"{fl} < {sl}",
                      f"< {price(s1, cur)}", price(f1, cur)),
            ]
            summary = (f"On {stamp(s.ts[i], s.timeframe)} the {fl} fell to {price(f1, cur)} and was thus below the "
                       f"{sl} ({price(s1, cur)}); on the previous candle it was still at {price(f0, cur)} "
                       f"(≥ {price(s0, cur)}).")
        out.append(Event(typ, direction, i, i, i - 1, title, summary, crit,
                         {"sma_fast": _f(f1), "sma_slow": _f(s1), "sma_fast_prev": _f(f0), "sma_slow_prev": _f(s0),
                          "close": _f(s.close[i])}, dict(p)))
    return out


def _pivots(x: F64, k: int, low: bool) -> list[int]:
    """Extreme points: candle i is a low/high if it beats the k candles on the left (not strictly) and on the right
    (strictly). A pivot is only confirmed k candles later."""
    res = []
    for i in range(k, len(x) - k):
        left, right = x[i - k:i], x[i + 1:i + k + 1]
        if low and x[i] <= left.min() and x[i] < right.min():
            res.append(i)
        elif not low and x[i] >= left.max() and x[i] > right.max():
            res.append(i)
    return res


def detect_rsi_divergences(s: Series) -> list[Event]:
    p = PARAMS["rsi_divergence"]
    k = p["pivot_window"]
    rsi = ind.rsi(s.close, p["rsi_period"])
    out: list[Event] = []
    cur = s.currency
    rl = f"RSI({p['rsi_period']})"
    for low in (True, False):
        series = s.low if low else s.high
        piv = [i for i in _pivots(series, k, low) if not np.isnan(rsi[i])]
        for a, b in zip(piv, piv[1:], strict=False):
            apart = b - a
            p1, p2, r1, r2 = series[a], series[b], rsi[a], rsi[b]
            diff_pct = (p1 - p2) / p1 * 100 if low else (p2 - p1) / p1 * 100  # >0: price further in the direction
            rsi_diff = (r2 - r1) if low else (r1 - r2)
            zone_ok = r1 < p["rsi_midline"] if low else r1 > p["rsi_midline"]
            if not (p["min_bars_apart"] <= apart <= p["max_bars_apart"] and diff_pct >= p["min_price_diff_pct"]
                    and rsi_diff >= p["min_rsi_diff"] and zone_ok):
                continue
            what, ext = ("low", "lower") if low else ("high", "higher")
            rsi_ext = "higher" if low else "lower"
            crit = [
                _crit(f"Distance between the price {what}s", "Candles between the extreme points",
                      f"{p['min_bars_apart']} to {p['max_bars_apart']}", str(apart)),
                _crit(f"{ext.capitalize()} price {what}",
                      f"{what.capitalize()} 2 {'<' if low else '>'} {what} 1, minimum difference "
                      f"{num(p['min_price_diff_pct'], 1)}%",
                      f"{'<' if low else '>'} {price(p1, cur)}", f"{price(p2, cur)} ({num(diff_pct)}% difference)"),
                _crit(f"{rsi_ext.capitalize()} RSI {what}", f"{rl} 2 {'>' if low else '<'} {rl} 1, at least "
                      f"{num(p['min_rsi_diff'], 1)} points difference",
                      f"{'>' if low else '<'} {num(r1, 1)}", f"{num(r2, 1)} ({num(rsi_diff, 1)} points)"),
                _crit(f"Position of {rl} at the first {what}", f"{rl} {'<' if low else '>'} {num(p['rsi_midline'], 0)}",
                      f"{'<' if low else '>'} {num(p['rsi_midline'], 0)}", num(r1, 1)),
            ]
            summary = (f"On {stamp(s.ts[b], s.timeframe)} the price formed a {ext} {what} ({price(p2, cur)} instead of "
                       f"{price(p1, cur)} on {stamp(s.ts[a], s.timeframe)}), while the {rl} formed a {rsi_ext} {what} "
                       f"({num(r2, 1)} instead of {num(r1, 1)}). This divergence is a descriptive "
                       f"observation, not a statement about what happens next.")
            out.append(Event("rsi_divergence", "up" if low else "down", b, b + k, a,
                             f"RSI divergence ({'price lower, RSI higher' if low else 'price higher, RSI lower'})",
                             summary, crit,
                             {"pivot1": {"ts": s.ts[a].isoformat(), "price": _f(p1), "rsi": _f(r1)},
                              "pivot2": {"ts": s.ts[b].isoformat(), "price": _f(p2), "rsi": _f(r2)},
                              "bars_apart": apart}, dict(p)))
    return sorted(out, key=lambda e: (e.index, e.direction or ""))


def detect_bollinger_breakouts(s: Series) -> list[Event]:
    p = PARAMS["bollinger"]
    mid, up, lo = ind.bollinger(s.close, p["period"], p["factor"])
    out: list[Event] = []
    cur = s.currency
    band = f"Bollinger band ({p['period']}, {num(p['factor'], 1)} σ)"
    for i in range(1, len(s)):
        if np.isnan(up[i]) or np.isnan(up[i - 1]):
            continue
        c1, c0 = s.close[i], s.close[i - 1]
        for direction, edge, edge0, above in (("up", up[i], up[i - 1], True), ("down", lo[i], lo[i - 1], False)):
            crossed = (c1 > edge and c0 <= edge0) if above else (c1 < edge and c0 >= edge0)
            if not crossed:
                continue
            side = "upper" if above else "lower"
            width = (up[i] - lo[i]) / mid[i] * 100
            pct_b = (c1 - lo[i]) / (up[i] - lo[i]) if up[i] != lo[i] else float("nan")
            crit = [
                _crit("Previous candle inside the band", f"Close {'≤ upper' if above else '≥ lower'} band",
                      f"{'≤' if above else '≥'} {price(edge0, cur)}", price(c0, cur)),
                _crit(f"Close outside the {side} band", f"Close {'>' if above else '<'} "
                      f"{'upper' if above else 'lower'} band", f"{'>' if above else '<'} {price(edge, cur)}",
                      price(c1, cur)),
            ]
            summary = (f"On {stamp(s.ts[i], s.timeframe)} the price closed at {price(c1, cur)} "
                       f"{'above' if above else 'below'} the {side} {band} ({price(edge, cur)}); "
                       f"the previous candle at {price(c0, cur)} was still inside. "
                       f"Band width {num(width)}% of the middle band ({price(mid[i], cur)}).")
            out.append(Event("bb_breakout", direction, i, i, i - 1,
                             f"Close outside the {side} Bollinger band", summary, crit,
                             {"close": _f(c1), "upper": _f(up[i]), "middle": _f(mid[i]), "lower": _f(lo[i]),
                              "close_prev": _f(c0), "bandwidth_pct": _f(width),
                              "percent_b": None if np.isnan(pct_b) else _f(pct_b)}, dict(p)))
    return out


def detect_volume_spikes(s: Series) -> list[Event]:
    p = PARAMS["volume_spike"]
    n = p["lookback"]
    out: list[Event] = []
    for i in range(n, len(s)):
        window = s.volume[i - n:i]
        v = s.volume[i]
        if np.isnan(v) or np.isnan(window).any():
            continue
        mean, std = window.mean(), window.std()
        if std == 0 or mean <= 0:
            continue
        z, ratio = (v - mean) / std, v / mean
        if z < p["min_z"] or ratio < p["min_ratio"]:
            continue
        crit = [
            _crit("Deviation from the mean of the preceding candles",
                  f"z = (volume − mean) / standard deviation, {n} preceding candles",
                  f"≥ {num(p['min_z'], 1)}", num(z, 1)),
            _crit("Ratio to the mean", f"Volume / mean of the {n} preceding candles",
                  f"≥ {num(p['min_ratio'], 1)}", f"{num(ratio, 1)}×"),
        ]
        summary = (f"On {stamp(s.ts[i], s.timeframe)} the volume was {num(v, 0)}, i.e. "
                   f"{num(ratio, 1)} times the mean of the {n} preceding candles ({num(mean, 0)}); "
                   f"z-value {num(z, 1)}.")
        out.append(Event("volume_spike", None, i, i, i - n, "Unusually high trading volume", summary, crit,
                         {"volume": _f(v), "mean": _f(mean), "std": _f(std), "z": _f(z), "ratio": _f(ratio)},
                         dict(p)))
    return out


def detect_all(s: Series) -> list[Event]:
    events = (detect_crosses(s) + detect_rsi_divergences(s) + detect_bollinger_breakouts(s)
              + detect_volume_spikes(s))
    for e in events:
        e.ts = s.ts[e.index]
    return sorted(events, key=lambda e: (e.index, e.type, e.direction or ""))
