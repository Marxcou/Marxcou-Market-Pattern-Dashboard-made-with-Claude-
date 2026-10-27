import { useQuery } from "@tanstack/react-query";
import { tr, type MessageKey } from "./i18n";
import {
  api, PENDING_POLL_MS, type IndicatorEventsResponse, type IndicatorEventType, type IndicatorsResponse, type MoveLinksResponse, type PatternCounts, type PatternsResponse,
} from "./api";


// 404 means: endpoint does not exist yet. That is an empty state with a reason, not an error and not a placeholder (Grundregel 6).
async function orMissing<T extends { empty_reason: string | null }>(path: string, empty: T): Promise<T> {
  try {
    return await api<T>(path);
  } catch (e) {
    if (e instanceof Error && e.message === "HTTP 404") return { ...empty, empty_reason: tr("analysis.missing") };
    throw e;
  }
}

// Pattern detection only works on daily and hourly candles (contract 3B).
export const patternTimeframe = (tfm: string) => (tfm === "1d" || tfm === "1h" ? tfm : null);

export interface IndicatorToggle { key: string; label: string; labelKey?: MessageKey; param: string; panel: "price" | "own"; seriesKey: string }
export const INDICATOR_TOGGLES: IndicatorToggle[] = [
  { key: "sma20", label: "SMA 20", param: "sma=20", panel: "price", seriesKey: "sma_20" },
  { key: "sma50", label: "SMA 50", param: "sma=50", panel: "price", seriesKey: "sma_50" },
  { key: "ema20", label: "EMA 20", param: "ema=20", panel: "price", seriesKey: "ema_20" },
  { key: "ema50", label: "EMA 50", param: "ema=50", panel: "price", seriesKey: "ema_50" },
  { key: "bb", label: "Bollinger Bands (20, 2)", labelKey: "ind.bb", param: "bb=20,2", panel: "price", seriesKey: "bb_20_2" },
  { key: "rsi", label: "RSI (14)", param: "rsi=14", panel: "own", seriesKey: "rsi_14" },
  { key: "macd", label: "MACD (12, 26, 9)", param: "macd=12,26,9", panel: "own", seriesKey: "macd_12_26_9" },
];

// sma/ema with several periods are combined into one comma-separated parameter.
export function indicatorQuery(active: string[]): string {
  const groups = new Map<string, string[]>();
  for (const t of INDICATOR_TOGGLES) {
    if (!active.includes(t.key)) continue;
    const [name, val] = t.param.split("=");
    groups.set(name, [...(groups.get(name) ?? []), val]);
  }
  return [...groups.entries()].map(([n, v]) => `${n}=${n === "sma" || n === "ema" ? v.join(",") : v[0]}`).join("&");
}

export const useIndicators = (id: string | undefined, timeframe: string, start: string | undefined, active: string[]) => {
  const q = indicatorQuery(active);
  return useQuery({
    queryKey: ["indicators", id, timeframe, start, q], enabled: !!id && q !== "",
    queryFn: () => orMissing<IndicatorsResponse>(`/instruments/${id}/indicators?timeframe=${timeframe}${start ? `&start=${encodeURIComponent(start)}` : ""}&${q}`,
      { instrument_id: Number(id), timeframe, algo_version: "", timestamps: [], indicators: [], sources: [], bars_fetched_at: null, empty_reason: null }),
    refetchInterval: 60_000,
  });
};

export const useIndicatorEvents = (id: string | undefined, timeframe: string, since: string | undefined) =>
  useQuery({
    queryKey: ["indicator-events", id, timeframe, since], enabled: !!id,
    queryFn: () => orMissing<IndicatorEventsResponse>(`/instruments/${id}/indicator-events?timeframe=${timeframe}${since ? `&since=${encodeURIComponent(since)}` : ""}&limit=200`,
      { events: [], next_cursor: null, empty_reason: null }),
    refetchInterval: 60_000,
  });

export const useMoveLinks = (id: string | undefined, timeframe: string, since: string | undefined) =>
  useQuery({
    queryKey: ["move-links", id, timeframe, since], enabled: !!id,
    queryFn: () => orMissing<MoveLinksResponse>(`/instruments/${id}/move-links?timeframe=${timeframe}${since ? `&since=${encodeURIComponent(since)}` : ""}`,
      { moves: [], note: tr("move.defaultNote"), empty_reason: null }),
    refetchInterval: 60_000,
  });

export const usePatterns = (id: string | undefined, timeframe: string | null, start: string | undefined, includeInvalid: boolean) =>
  useQuery({
    queryKey: ["patterns", id, timeframe, start, includeInvalid], enabled: !!id && timeframe != null,
    queryFn: () => orMissing<PatternsResponse>(`/instruments/${id}/patterns?timeframe=${timeframe}${includeInvalid ? "&include_invalid=true" : ""}${start ? `&start=${encodeURIComponent(start)}` : ""}`,
      { instrument: { id: Number(id), symbol: "", name: "", isin: null, exchange: "", currency: "" }, timeframe: timeframe ?? "", detections: [], zones: [], data_basis: null, algo_version: "", params_hash: "", computed_at: null, empty_reason: null }),
    refetchInterval: (q) => (q.state.data?.pending ? PENDING_POLL_MS : 60_000),
  });

export const usePatternCounts = () =>
  useQuery({
    queryKey: ["pattern-counts"],
    queryFn: () => orMissing<PatternCounts>("/patterns/counts", { counts: {}, empty_reason: null }),
    refetchInterval: 60_000,
  });

export const EVENT_SHORT: Record<IndicatorEventType, string> = {
  golden_cross: "GC", death_cross: "DC", rsi_divergence: "RSI", bb_breakout: "BB", volume_spike: "Vol",
};
const EVENT_KEY: Record<IndicatorEventType, MessageKey> = {
  golden_cross: "event.goldenCross", death_cross: "event.deathCross", rsi_divergence: "event.rsiDivergence", bb_breakout: "event.bbBreakout", volume_spike: "event.volumeSpike",
};
export const eventName = (t: IndicatorEventType) => tr(EVENT_KEY[t]);

// Status keys come from the backend ("in_bildung", "bestaetigt", "ungueltig"); unknown ones fall back to status_label.
export const statusText = (status: string, fallback: string) => {
  const key = `pattern.status.${status}` as MessageKey;
  const s = tr(key);
  return s === key ? fallback : s;
};

// For the symmetrical triangle (direction "offen") both levels are breakout levels: a closing price outside one of the
// lines resolves the pattern. It only becomes invalid when the apex is reached without a breakout or the deadline passes.
export function levelLabels(direction: string): { confirmation: string; invalidation: string } {
  return direction === "offen"
    ? { confirmation: tr("pattern.levels.breakoutUp"), invalidation: tr("pattern.levels.breakoutDown") }
    : { confirmation: tr("pattern.levels.confirm"), invalidation: tr("pattern.levels.invalid") };
}
