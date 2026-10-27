import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render as rtlRender, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./lib/auth";
import { LanguageProvider } from "./lib/i18n";

// The UI tests check the German texts; the language is therefore fixed to German.
const GermanUi = ({ children }: { children: ReactNode }) => <LanguageProvider lang="de">{children}</LanguageProvider>;
export const render = (ui: ReactElement, options?: RenderOptions) => rtlRender(ui, { wrapper: GermanUi, ...options });

export const SOURCE = { key: "alpaca", name: "Alpaca", homepage: "https://alpaca.markets", terms_url: "https://alpaca.markets/disclosures", delay_text: "Echtzeit (IEX)" };
export const INSTRUMENT = { id: 1, symbol: "AAPL", name: "Apple Inc.", isin: "US0378331005", exchange: "XNAS", currency: "USD" };
export const ME = { user: { id: 1, email: "a@b.de", display_name: "Luca", role: "admin" }, csrf_token: "t" };

// Replaces fetch with fixed responses per path (without query string); a number stands for an HTTP status.
export function mockApi(routes: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const key = url.replace(/^\/api/, "").split("?")[0];
    const r = key === "/meta" ? { demo_mode: false, timezone: "Europe/Berlin", disclaimer: "" } : routes[key];
    if (typeof r === "number") return new Response("{}", { status: r });
    if (r === undefined) return new Response("{}", { status: 404 });
    return new Response(JSON.stringify(r), { status: 200 });
  }));
}

export function renderApp(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <LanguageProvider lang="de"><AuthProvider><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AuthProvider></LanguageProvider>
    </QueryClientProvider>,
  );
}
