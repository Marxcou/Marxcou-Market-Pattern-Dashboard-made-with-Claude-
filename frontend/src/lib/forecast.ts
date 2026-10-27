import { useQuery } from "@tanstack/react-query";
import { tr, type MessageKey } from "./i18n";
import { api, PENDING_POLL_MS, type ForecastExamplePath, type ForecastMetric, type ForecastResponse, type ForecastStep, type PatternDetection, type QuantileKey } from "./api";


// Forecasts run on daily candles (contract phase 4); there is no corridor for other timeframes.
export const forecastTimeframe = (tfm: string) => (tfm === "1d" ? tfm : null);
export const HORIZONS = [5, 10, 20] as const; // the backend delivers at most 20 candles

// The three probability ranges: middle 50%, middle 80%, middle 95% of the simulated paths (Grundregel 4).
export interface BandSpec { level: 50 | 80 | 95; lower: QuantileKey; upper: QuantileKey }
// Opaque blended colors of the bands on the chart background; the legend in the panel uses the same values.
export const BAND_FILL = { 95: "#173a5a", 80: "#1d5479", 50: "#26739f" } as const;
export const BANDS: BandSpec[] = [
  { level: 95, lower: "2.5", upper: "97.5" },
  { level: 80, lower: "10", upper: "90" },
  { level: 50, lower: "25", upper: "75" },
];

// Central path (median per step) and example paths: lines only inside the corridor, without an end-value label.
export const MEDIAN_COLOR = "#f1f5f9";
export const EXAMPLE_COLOR = "rgba(203, 213, 225, 0.4)";

export const medianSeries = (steps: ForecastStep[]) => validSteps(steps).map((s) => ({ ts: s.ts, v: s.quantiles["50"] }));

// Only paths with finite values throughout; incomplete ones are discarded instead of filled in (Grundregel 6).
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
        // Missing forecasts arrive as 200 with empty_reason; 404 (endpoint or instrument unknown) is shown as an empty state as well. Empty state with a reason, no placeholder data (Grundregel 6).
        if (e instanceof Error && e.message === "HTTP 404") {
          return { instrument_id: Number(id), timeframe: timeframe ?? "", method: null, horizon_bars: horizon, based_on_until: null, last_close: null,
            generated_at: null, algo_version: "", steps: [], backtest: null, data_basis: null, empty_reason: tr("fc.missing") };
        }
        throw e;
      }
    },
    refetchInterval: (q) => (q.state.data?.pending ? PENDING_POLL_MS : 5 * 60_000),
  });

// Steps that deliver all quantiles as finite numbers; everything else is discarded instead of filled in.
export function validSteps(steps: ForecastStep[]): ForecastStep[] {
  const keys: QuantileKey[] = ["2.5", "10", "25", "50", "75", "90", "97.5"];
  return steps.filter((s) => keys.every((k) => Number.isFinite(s.quantiles?.[k]))).sort((a, b) => a.ts.localeCompare(b.ts));
}

export interface BandPoint { ts: string; lower: number; upper: number }
export const bandSeries = (steps: ForecastStep[], b: BandSpec): BandPoint[] =>
  validSteps(steps).map((s) => ({ ts: s.ts, lower: s.quantiles[b.lower], upper: s.quantiles[b.upper] }));

// Where does a level lie relative to the bands at the end of the horizon? Purely descriptive, no probability for an event.
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

// Smaller error is better: ratio of model to the reference "price stays the same".
export function metricVsNaive(m: ForecastMetric): { ratio: number | null; text: string } {
  if (m.naive == null || m.model == null || !(m.naive > 0) || !Number.isFinite(m.model)) return { ratio: null, text: tr("fcbt.vs.na") };
  const ratio = m.model / m.naive;
  if (Math.abs(ratio - 1) < 0.005) return { ratio, text: tr("fcbt.vs.same") };
  return { ratio, text: tr(ratio < 1 ? "fcbt.vs.lower" : "fcbt.vs.higher") };
}

// Describes the coverage: should the 80% band have contained about 80% of the outcomes?
export function coverageNote(nominal: number, observed: number): string {
  const diff = observed - nominal;
  if (Math.abs(diff) <= 0.05) return tr("fcbt.cov.close");
  return tr(diff < 0 ? "fcbt.cov.narrow" : "fcbt.cov.wide");
}
