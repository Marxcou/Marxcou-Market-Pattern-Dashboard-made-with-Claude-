"""Description of all pattern types for /patterns/catalog ("How is this calculated?")."""
from typing import Any

from app.analysis.params import ALGO_VERSION, Params, params_doc
from app.analysis.patterns import double, flags, head_shoulders, triangles

_DOUBLE = [
    ("extrem_abweichung", "Deviation between the two extreme points", "at most doppel.max_extrem_abweichung_pct", True),
    ("tiefe", "Depth of the intermediate point", "at least doppel.min_tiefe_pct", True),
    ("abstand", "Distance between the extreme points",
     "between doppel.min_abstand_kerzen and doppel.max_abstand_kerzen", True),
    ("vortrend", "Prior trend", "at least doppel.min_vortrend_pct", True),
    ("volumen", "Volume at the second extreme point", "lower than at the first (only with volume data)", False),
]
_HS = [
    ("kopf_ueberhang", "Head relative to the shoulders", "at least kopf_schulter.min_kopf_ueberhang_pct", True),
    ("schulter_abweichung", "Symmetry of the shoulders", "at most kopf_schulter.max_schulter_abweichung_pct", True),
    ("nacken_neigung", "Slope of the neckline", "at most kopf_schulter.max_nacken_neigung_pct", True),
    ("zeit_symmetrie", "Time symmetry", "Ratio between kopf_schulter.min_zeit_verhaeltnis and "
     "kopf_schulter.max_zeit_verhaeltnis", True),
    ("vortrend", "Prior trend", "at least kopf_schulter.min_vortrend_pct", True),
    ("volumen", "Volume at the right shoulder", "lower than at the head (only with volume data)", False),
]
_TRI = [
    ("form", "Course of the lines", "Slopes according to pattern type (dreieck_keil.flach_steigung_pct, "
     "dreieck_keil.min_steigung_pct)", True),
    ("verengung", "Narrowing of the range", "at least dreieck_keil.min_verengung_pct", True),
    ("anpassung", "Position of the turning points on the lines", "at most dreieck_keil.max_anpassung_pct", True),
    ("beruehrungen", "Touches per line", "at least 2", True),
    ("innerhalb", "Closing prices between the lines", "at least dreieck_keil.min_anteil_innerhalb_pct", True),
    ("volumen", "Volume trend", "second half lower than first (only with volume data)", False),
]
_FLAG = [
    ("stange", "Flagpole", "at least flagge.min_stange_pct within at most flagge.max_stange_kerzen candles", True),
    ("ruecksetzer", "Retracement within the consolidation", "at most flagge.max_ruecksetzer_pct", True),
    ("neigung", "Slope of the consolidation", "at most flagge.max_neigung_anteil_pct of the flagpole", True),
    ("form", "Shape of the channel", "Flag: parallel (flagge.max_parallel_abweichung_pct); Pennant: converging "
     "(flagge.wimpel_min_steigung_pct)", True),
    ("innerhalb", "Closing prices inside the channel", "at least flagge.min_anteil_innerhalb_pct", True),
    ("dauer", "Duration of the consolidation", "flagge.min_flagge_kerzen to flagge.max_flagge_kerzen", True),
    ("volumen", "Volume during the consolidation", "lower than in the flagpole (only with volume data)", False),
]

_GROUPS = {"doppel": ["pivots", "status", "doppel", "volumen"],
           "kopf_schulter": ["pivots", "status", "kopf_schulter", "volumen"],
           "dreieck_keil": ["pivots", "status", "dreieck_keil", "volumen"], "flagge": ["flagge", "volumen"]}

ENTRIES: list[tuple[str, str, str, str, str, list[tuple[str, str, str, bool]], dict[str, float]]] = [
    ("doppelboden", "Double bottom", "aufwärts", "doppel",
     "Two lows of similar depth with an intermediate high after a decline. Confirmed when a closing price is above "
     "the intermediate high (neckline).", _DOUBLE, double.WEIGHTS),
    ("doppelhoch", "Double top", "abwärts", "doppel",
     "Two highs of similar height with an intermediate low after an advance. Confirmed when a closing price is "
     "below the intermediate low (neckline).", _DOUBLE, double.WEIGHTS),
    ("kopf_schulter", "Head and shoulders", "abwärts", "kopf_schulter",
     "Three highs, the middle one (head) the highest and the outer ones (shoulders) of similar height. Confirmed by "
     "a closing price below the neckline through the two intermediate lows.", _HS, head_shoulders.WEIGHTS),
    ("kopf_schulter_invers", "Inverse head and shoulders", "aufwärts", "kopf_schulter",
     "Mirror image of the head and shoulders formation with three lows. Confirmed by a closing price above the "
     "neckline.", _HS, head_shoulders.WEIGHTS),
    ("dreieck_aufsteigend", "Ascending triangle", "aufwärts", "dreieck_keil",
     "Horizontal upper line, rising lower line. Confirmed by a closing price above the upper line.",
     _TRI, triangles.WEIGHTS),
    ("dreieck_absteigend", "Descending triangle", "abwärts", "dreieck_keil",
     "Horizontal lower line, falling upper line. Confirmed by a closing price below the lower line.",
     _TRI, triangles.WEIGHTS),
    ("dreieck_symmetrisch", "Symmetrical triangle", "offen", "dreieck_keil",
     "Falling upper line and rising lower line. The direction only results from the breakout (closing price "
     "outside one of the lines).", _TRI, triangles.WEIGHTS),
    ("keil_steigend", "Rising wedge", "abwärts", "dreieck_keil",
     "Both lines rise, the lower one more steeply, and the range narrows. Confirmed by a closing price below the "
     "lower line.", _TRI, triangles.WEIGHTS),
    ("keil_fallend", "Falling wedge", "aufwärts", "dreieck_keil",
     "Both lines fall, the upper one more steeply, and the range narrows. Confirmed by a closing price above the "
     "upper line.", _TRI, triangles.WEIGHTS),
    ("flagge_aufwaerts", "Flag after an advance", "aufwärts", "flagge",
     "Steep advance (flagpole) followed by a narrow, horizontal or slightly falling channel. Confirmed by a "
     "closing price above the upper channel line.", _FLAG, flags.WEIGHTS),
    ("flagge_abwaerts", "Flag after a decline", "abwärts", "flagge",
     "Steep decline followed by a narrow, horizontal or slightly rising channel. Confirmed by a closing price "
     "below the lower channel line.", _FLAG, flags.WEIGHTS),
    ("wimpel_aufwaerts", "Pennant after an advance", "aufwärts", "flagge",
     "Steep advance followed by converging lines. Confirmed by a closing price above the upper line.",
     _FLAG, flags.WEIGHTS),
    ("wimpel_abwaerts", "Pennant after a decline", "abwärts", "flagge",
     "Steep decline followed by converging lines. Confirmed by a closing price below the lower line.",
     _FLAG, flags.WEIGHTS),
]

PATTERN_NAMES = {e[0]: e[1] for e in ENTRIES}


def catalog(params: Params) -> list[dict[str, Any]]:
    out = []
    for ptype, name, direction, group, description, crits, weights in ENTRIES:
        out.append({
            "pattern_type": ptype, "name": name, "direction_if_confirmed": direction, "description": description,
            "criteria": [{"key": k, "name": n, "rule": r, "required": req, "weight": weights[k]}
                         for k, n, r, req in crits],
            "params": params_doc(_GROUPS[group], params), "algo_version": ALGO_VERSION,
        })
    return out
