import type { Bar } from "./api";

export interface Range { label: string; timeframe: "1m" | "5m" | "1h" | "1d"; days: number }

export const RANGES: Range[] = [
  { label: "1T", timeframe: "5m", days: 1 },
  { label: "1W", timeframe: "1h", days: 7 },
  { label: "1M", timeframe: "1d", days: 31 },
  { label: "6M", timeframe: "1d", days: 183 },
  { label: "1J", timeframe: "1d", days: 366 },
  { label: "5J", timeframe: "1d", days: 1830 },
];

const DAY_MS = 86_400_000;

// Query start with a buffer for weekends and holidays.
export const rangeStart = (r: Range, now = Date.now()) => new Date(now - (r.days + 5) * DAY_MS).toISOString();

// The window is anchored to the last available data point, not to the clock: so "1D" shows the last trading day on weekends too.
export function windowBars(bars: Bar[], r: Range): Bar[] {
  if (bars.length === 0) return bars;
  const last = new Date(bars[bars.length - 1].ts_utc).getTime();
  return bars.filter((b) => new Date(b.ts_utc).getTime() >= last - r.days * DAY_MS);
}
