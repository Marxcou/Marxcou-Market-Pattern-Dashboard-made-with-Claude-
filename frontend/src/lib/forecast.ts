import { useQuery } from "@tanstack/react-query";
import { tr, type MessageKey } from "./i18n";
import { api, PENDING_POLL_MS, type ForecastExamplePath, type ForecastMetric, type ForecastResponse, type ForecastStep, type PatternDetection, type QuantileKey } from "./api";


// Prognosen laufen auf Tageskerzen (Vertrag Phase 4); für andere Zeiträume gibt es keinen Korridor.
export const forecastTimeframe = (tfm: string) => (tfm === "1d" ? tfm : null);
export const HORIZONS = [5, 10, 20] as const; // das Backend liefert höchstens 20 Kerzen

// Die drei Wahrscheinlichkeitsbereiche: Mitte-50 %, Mitte-80 %, Mitte-95 % der simulierten Verläufe (Grundregel 4).
export interface BandSpec { level: 50 | 80 | 95; lower: QuantileKey; upper: QuantileKey }
// Undurchsichtige Mischfarben der Bänder auf dem Chart-Hintergrund; die Legende im Panel nutzt dieselben Werte.
export const BAND_FILL = { 95: "#173a5a", 80: "#1d5479", 50: "#26739f" } as const;
export const BANDS: BandSpec[] = [
  { level: 95, lower: "2.5", upper: "97.5" },
  { level: 80, lower: "10", upper: "90" },
  { level: 50, lower: "25", upper: "75" },
];

// Mittlerer Verlauf (Median je Schritt) und Beispielpfade: nur Linien innerhalb des Korridors, ohne Endwert-Beschriftung.
export const MEDIAN_COLOR = "#f1f5f9";
export const EXAMPLE_COLOR = "rgba(203, 213, 225, 0.4)";

export const medianSeries = (steps: ForecastStep[]) => validSteps(steps).map((s) => ({ ts: s.ts, v: s.quantiles["50"] }));

// Nur Pfade mit durchgehend endlichen Werten; unvollständige werden verworfen statt aufgefüllt (Grundregel 6).
export const validExamplePaths = (paths: ForecastExamplePath[] | undefined): ForecastExamplePath[] =>
  (paths ?? []).filter((p) => p.steps.length > 0 && p.steps.every((s) => Number.isFinite(s.close)))
    .map((p) => ({ ...p, steps: [...p.steps].sort((a, b) => a.ts.localeCompare(b.ts)) }));

export const useForecast = (id: string | undefined, timeframe: string | null, horizon: number, enabled: boolean) =>
  useQuery({
    queryKey: ["forecast", id, timeframe, horizon], enabled: enabled && !!id && timeframe != null,
    queryFn: async (): Promise<ForecastResponse> => {
      try {
        return await api<ForecastResponse>(`/instruments/${id}/forecast?timeframe=${timeframe}&horizon=${horizon}`);
      } catch (e) {
        // Fehlende Prognosen kommen als 200 mit empty_reason; 404 (Endpunkt oder Instrument unbekannt) wird ebenso als Leerzustand gezeigt. Leerzustand mit Grund, keine Platzhalterdaten (Grundregel 6).
        if (e instanceof Error && e.message === "HTTP 404") {
          return { instrument_id: Number(id), timeframe: timeframe ?? "", method: null, horizon_bars: horizon, based_on_until: null, last_close: null,
            generated_at: null, algo_version: "", steps: [], backtest: null, data_basis: null, empty_reason: tr("fc.missing") };
        }
        throw e;
      }
    },
    refetchInterval: (q) => (q.state.data?.pending ? PENDING_POLL_MS : 5 * 60_000),
  });

// Schritte, die alle Quantile als endliche Zahlen liefern; alles andere wird verworfen statt aufgefüllt.
export function validSteps(steps: ForecastStep[]): ForecastStep[] {
  const keys: QuantileKey[] = ["2.5", "10", "25", "50", "75", "90", "97.5"];
  return steps.filter((s) => keys.every((k) => Number.isFinite(s.quantiles?.[k]))).sort((a, b) => a.ts.localeCompare(b.ts));
}

export interface BandPoint { ts: string; lower: number; upper: number }
export const bandSeries = (steps: ForecastStep[], b: BandSpec): BandPoint[] =>
  validSteps(steps).map((s) => ({ ts: s.ts, lower: s.quantiles[b.lower], upper: s.quantiles[b.upper] }));

// Wo liegt ein Niveau relativ zu den Bändern am Ende des Horizonts? Rein beschreibend, keine Wahrscheinlichkeit für ein Ereignis.
export function levelPosition(level: number, last: ForecastStep | undefined): { inside: 50 | 80 | 95 | null; text: string } {
  if (!last) return { inside: null, text: tr("fc.pos.none") };
  const q = last.quantiles;
  const inside = ([50, 80, 95] as const).find((l) => {
    const b = BANDS.find((x) => x.level === l)!;
    return level >= q[b.lower] && level <= q[b.upper];
  });
  if (inside) return { inside, text: tr("fc.pos.inside", { n: inside }) };
  return { inside: null, text: tr("fc.pos.outside", { dir: tr(level > q["97.5"] ? "fc.pos.above" : "fc.pos.below") }) };
}

export interface ScenarioLevel { key: string; label: string; price: number; color: string }
const LEVEL_COLOR: Record<string, string> = { bestaetigung: "#a78bfa", scheitern: "#f472b6", ausbruch_oben: "#a78bfa", ausbruch_unten: "#f472b6" };
export const scenarioLevels = (p: PatternDetection | null): ScenarioLevel[] =>
  (p?.scenarios ?? []).flatMap((s, i) => s.trigger_level == null ? [] : [{ key: `${p!.id}-${s.kind}-${i}`, label: `${s.title} (${p!.name})`, price: s.trigger_level, color: LEVEL_COLOR[s.kind] ?? "#94a3b8" }]);

export const metricName = (m: ForecastMetric) => {
  const key = `fcbt.metric.${m.key}` as MessageKey;
  const s = tr(key);
  return s !== key ? s : m.name ?? m.key;
};

// Kleiner Fehler ist besser: Verhältnis Modell zu Referenz "Kurs bleibt gleich".
export function metricVsNaive(m: ForecastMetric): { ratio: number | null; text: string } {
  if (m.naive == null || m.model == null || !(m.naive > 0) || !Number.isFinite(m.model)) return { ratio: null, text: tr("fcbt.vs.na") };
  const ratio = m.model / m.naive;
  if (Math.abs(ratio - 1) < 0.005) return { ratio, text: tr("fcbt.vs.same") };
  return { ratio, text: tr(ratio < 1 ? "fcbt.vs.lower" : "fcbt.vs.higher") };
}

// Beschreibt die Abdeckung: hätte das 80-%-Band etwa 80 % der Ergebnisse enthalten sollen?
export function coverageNote(nominal: number, observed: number): string {
  const diff = observed - nominal;
  if (Math.abs(diff) <= 0.05) return tr("fcbt.cov.close");
  return tr(diff < 0 ? "fcbt.cov.narrow" : "fcbt.cov.wide");
}
