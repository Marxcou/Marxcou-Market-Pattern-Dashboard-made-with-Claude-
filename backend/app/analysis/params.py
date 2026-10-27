"""Documented parameters of the pattern detection. Every detection stores the values used, their hash
and ALGO_VERSION so it is reproducible. Changes to rules increase ALGO_VERSION."""
import hashlib
import json
from dataclasses import dataclass
from typing import Any

ALGO_VERSION = "1.0.0"
TEXT_VERSION = "en-1"  # bump when the language or wording of stored texts changes (forces a rescan)


@dataclass(frozen=True)
class Param:
    value: float
    unit: str
    description: str


PARAM_DOCS: dict[str, dict[str, Param]] = {
    "pivots": {
        "atr_periode": Param(14, "candles", "Period of the ATR (Average True Range after Wilder)"),
        "atr_faktor": Param(2.0, "factor", "A turning point is fixed once the price has moved away from it by at "
                            "least this many ATR"),
        "min_bewegung_pct": Param(1.0, "%", "Minimum move for a turning point, if larger than the ATR threshold"),
    },
    "status": {
        "invalidierung_puffer_pct": Param(1.5, "%", "Distance beyond the extreme point from which a pattern "
                                          "is considered invalid (double top/bottom and head and shoulders)"),
        "frist_min_kerzen": Param(10, "candles", "Minimum deadline for confirmation after the pattern end"),
        "frist_max_kerzen": Param(60, "candles", "Maximum deadline for confirmation after the pattern end; "
                                 "otherwise the pattern width"),
    },
    "doppel": {
        "max_extrem_abweichung_pct": Param(1.5, "%", "Maximum deviation of the two highs or lows (ideal value 0%)"),
        "min_abstand_kerzen": Param(10, "candles", "Minimum distance between the two extreme points"),
        "max_abstand_kerzen": Param(120, "candles", "Maximum distance between the two extreme points"),
        "ideal_abstand_min": Param(20, "candles", "Distance from which the sub-score is 1"),
        "ideal_abstand_max": Param(80, "candles", "Distance up to which the sub-score is 1"),
        "min_tiefe_pct": Param(3.0, "%", "Minimum distance of the intermediate high/low from the nearer extreme point"),
        "ideal_tiefe_pct": Param(8.0, "%", "Depth from which the sub-score is 1"),
        "min_vortrend_pct": Param(5.0, "%", "Minimum move from the previous turning point to the first extreme point"),
        "ideal_vortrend_pct": Param(15.0, "%", "Prior trend from which the sub-score is 1"),
    },
    "kopf_schulter": {
        "min_kopf_ueberhang_pct": Param(2.0, "%", "Head lies at least this far beyond the higher shoulder"),
        "ideal_kopf_ueberhang_pct": Param(6.0, "%", "Overhang from which the sub-score is 1"),
        "max_schulter_abweichung_pct": Param(5.0, "%", "Maximum deviation of the two shoulders (ideal value 0%)"),
        "max_nacken_neigung_pct": Param(5.0, "%", "Maximum difference of the two neck points (ideal value 0%)"),
        "min_zeit_verhaeltnis": Param(0.5, "factor", "Duration left side / right side, minimum"),
        "max_zeit_verhaeltnis": Param(2.0, "factor", "Duration left side / right side, maximum (ideal value 1)"),
        "min_breite_kerzen": Param(15, "candles", "Minimum width from left to right shoulder"),
        "max_breite_kerzen": Param(250, "candles", "Maximum width from left to right shoulder"),
        "min_vortrend_pct": Param(5.0, "%", "Minimum move from the previous turning point to the left shoulder"),
        "ideal_vortrend_pct": Param(15.0, "%", "Prior trend from which the sub-score is 1"),
    },
    "dreieck_keil": {
        "min_pivots": Param(4, "count", "Minimum number of turning points (at least 2 on each line)"),
        "max_pivots": Param(6, "count", "Maximum number of turning points per candidate"),
        "min_breite_kerzen": Param(15, "candles", "Minimum duration"),
        "max_breite_kerzen": Param(150, "candles", "Maximum duration"),
        "flach_steigung_pct": Param(0.05, "% per candle", "A line counts as horizontal up to this slope"),
        "min_steigung_pct": Param(0.05, "% per candle", "A line counts as rising/falling from this slope"),
        "max_anpassung_pct": Param(1.5, "%", "Maximum distance of a turning point from its line"),
        "min_verengung_pct": Param(20.0, "%", "Minimum narrowing of the range from start to end"),
        "ideal_verengung_pct": Param(50.0, "%", "Narrowing from which the sub-score is 1"),
        "toleranz_atr": Param(0.5, "factor", "Tolerance around the lines for closing prices inside, in ATR"),
        "min_anteil_innerhalb_pct": Param(90.0, "%", "Minimum share of closing prices between the lines"),
    },
    "flagge": {
        "min_stange_pct": Param(8.0, "%", "Minimum move of the flagpole"),
        "ideal_stange_pct": Param(15.0, "%", "Flagpole from which the sub-score is 1"),
        "min_stange_kerzen": Param(3, "candles", "Minimum duration of the flagpole"),
        "max_stange_kerzen": Param(15, "candles", "Maximum duration of the flagpole"),
        "min_flagge_kerzen": Param(5, "candles", "Minimum duration of the consolidation"),
        "max_flagge_kerzen": Param(20, "candles", "Maximum duration of the consolidation"),
        "max_ruecksetzer_pct": Param(50.0, "%", "Maximum retracement within the consolidation, in % of the flagpole"),
        "ideal_ruecksetzer_pct": Param(25.0, "%", "Retracement up to which the sub-score is 1"),
        "max_parallel_abweichung_pct": Param(0.15, "% per candle", "Flag: maximum difference of the slopes"),
        "max_gegen_steigung_pct": Param(0.05, "% per candle", "Flag: midline at most this steep in the direction "
                                        "of the flagpole (otherwise not a consolidation)"),
        "max_neigung_anteil_pct": Param(40.0, "%", "Slope of the channel midline at most this share of the mean "
                                        "slope of the flagpole (otherwise more a trend reversal than a consolidation)"),
        "wimpel_min_steigung_pct": Param(0.02, "% per candle", "Pennant: upper line falls and lower line rises by "
                                         "at least this much each"),
        "toleranz_atr": Param(0.5, "factor", "Tolerance around the channel lines for closing prices, in ATR"),
        "min_anteil_innerhalb_pct": Param(90.0, "%", "Minimum share of closing prices inside the channel"),
        "ausbruch_frist_kerzen": Param(10, "candles", "Deadline for the breakout after the end of the consolidation"),
    },
    "volumen": {
        "ideal_verhaeltnis": Param(0.7, "factor", "Volume ratio (later/earlier) up to which the sub-score is 1"),
        "grenz_verhaeltnis": Param(1.3, "factor", "Volume ratio from which the sub-score is 0"),
        "fenster_kerzen": Param(2, "candles", "Candles left and right of a turning point for the mean volume"),
    },
    "zonen": {
        "rueckblick_kerzen": Param(500, "candles", "Only turning points from this period form zones"),
        "toleranz_atr": Param(0.5, "factor", "Zone width as a multiple of the mean ATR"),
        "min_toleranz_pct": Param(0.75, "%", "Minimum zone width in % of the last closing price"),
        "min_beruehrungen": Param(3, "count", "Minimum number of turning points in the zone"),
        "ideal_beruehrungen": Param(6, "count", "Touches from which the sub-score is 1"),
        "min_zeitspanne_kerzen": Param(20, "candles", "Minimum distance between first and last touch"),
        "ideal_zeitspanne_kerzen": Param(120, "candles", "Time span from which the sub-score is 1"),
        "ideal_aktualitaet_kerzen": Param(20, "candles", "Last touch at most this long ago: sub-score 1"),
        "max_aktualitaet_kerzen": Param(250, "candles", "Last touch this long ago: sub-score 0"),
        "max_zonen": Param(8, "count", "Maximum number of displayed zones (those with the highest confidence)"),
    },
}

Params = dict[str, dict[str, float]]


def default_params() -> Params:
    return {group: {k: p.value for k, p in items.items()} for group, items in PARAM_DOCS.items()}


def params_hash(params: Params) -> str:
    blob = json.dumps({"v": ALGO_VERSION, "t": TEXT_VERSION, "p": params}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:8]


def params_doc(groups: list[str], params: Params) -> list[dict[str, Any]]:
    """Parameters with description for /patterns/catalog (values actually used)."""
    return [
        {"key": f"{g}.{k}", "value": params[g][k], "unit": p.unit, "description": p.description}
        for g in groups for k, p in PARAM_DOCS[g].items()
    ]


def subset(groups: list[str], params: Params) -> dict[str, float]:
    return {f"{g}.{k}": v for g in groups for k, v in params[g].items()}
