// Access to the labeled demo data (backend/app/e2e_seed.py). Everything here is invented.
import { expect, type APIRequestContext } from "@playwright/test";

export const DEMO_SYMBOL = "DEMOA"; // double bottom, news, forecast
export const DEMO_SYMBOL_2 = "DEMOB"; // double bottom forming, without news, for adding in tests

export interface DemoInstrument { id: number; symbol: string; name: string }

export async function findInstrument(request: APIRequestContext, symbol: string): Promise<DemoInstrument> {
  const res = await request.get(`/api/instruments/search?q=${symbol}`);
  expect(res.ok()).toBeTruthy();
  const hit = ((await res.json()) as DemoInstrument[]).find((i) => i.symbol === symbol);
  expect(hit, `Demo instrument ${symbol} is missing (was e2e_seed run?)`).toBeTruthy();
  return hit as DemoInstrument;
}

export async function setWatchlist(request: APIRequestContext, csrf: string, symbols: string[]): Promise<void> {
  const headers = { "X-CSRF-Token": csrf };
  const current = (await (await request.get("/api/watchlist")).json()) as { id: number }[];
  for (const i of current) await request.delete(`/api/watchlist/${i.id}`, { headers });
  for (const s of symbols) {
    const inst = await findInstrument(request, s);
    const r = await request.post("/api/watchlist", { data: { instrument_id: inst.id }, headers });
    expect(r.ok()).toBeTruthy();
  }
}
