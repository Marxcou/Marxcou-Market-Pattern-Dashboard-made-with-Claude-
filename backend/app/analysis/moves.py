"""Notable price moves: return (close to previous close) or volume deviate strongly from the behavior of the
preceding candles. The link to news is purely temporal (core rule: do not claim causality)."""
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import numpy as np

from app.analysis.events import Series

ALGO_VERSION = "move-links-2"
NOTE = "Coinciding in time, no statement about cause."
TIMEFRAME_DELTA = {"1m": timedelta(minutes=1), "5m": timedelta(minutes=5), "1h": timedelta(hours=1),
                   "1d": timedelta(days=1)}
# Time window around the candle in which first publications count as "matching in time" (minutes)
WINDOWS = {"1m": (30, 5), "5m": (60, 15), "1h": (180, 60), "1d": (1440, 360)}
PARAMS: dict[str, Any] = {"lookback_bars": 60, "z_threshold": 3.0}


@dataclass
class Move:
    index: int
    return_pct: float
    return_z: float | None
    volume_z: float | None
    reasons: list[str]


def params_for(timeframe: str) -> dict[str, Any]:
    before, after = WINDOWS[timeframe]
    return {**PARAMS, "window_before_minutes": before, "window_after_minutes": after}


def detect_moves(s: Series) -> list[Move]:
    n, thr = PARAMS["lookback_bars"], PARAMS["z_threshold"]
    ret = np.full(len(s), np.nan)
    ret[1:] = s.close[1:] / s.close[:-1] - 1
    out: list[Move] = []
    for i in range(n + 1, len(s)):
        window = ret[i - n:i]
        std = window.std(ddof=1)
        rz = (ret[i] - window.mean()) / std if std > 0 else float("nan")
        vz: float | None = None
        vwin = s.volume[i - n:i]
        if not np.isnan(s.volume[i]) and not np.isnan(vwin).any() and vwin.std(ddof=1) > 0:
            vz = float((s.volume[i] - vwin.mean()) / vwin.std(ddof=1))
        reasons = []
        if not np.isnan(rz) and abs(rz) >= thr:
            reasons.append("return_z")
        if vz is not None and vz >= thr:
            reasons.append("volume_z")
        if reasons:
            out.append(Move(i, float(ret[i] * 100), float(rz) if not np.isnan(rz) else None, vz, reasons))
    return out
