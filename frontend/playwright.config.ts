import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against the built frontend (vite preview) and a real backend with a fresh SQLite DB
// that e2e/start-backend.mjs fills with labeled demo data (DEMO_MODE=true). No real market data,
// no API keys, no network access to providers.
const PORT = Number(process.env.E2E_WEB_PORT ?? 4173);
const API_PORT = Number(process.env.E2E_API_PORT ?? 8000); // vite.config.ts forwards /api and /ws to port 8000

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  // The interface starts in English; these tests check the German version (language choice "lang" in localStorage).
  use: {
    baseURL: `http://localhost:${PORT}`, locale: "de-DE", timezoneId: "Europe/Berlin", trace: "retain-on-failure",
    storageState: { cookies: [], origins: [{ origin: `http://localhost:${PORT}`, localStorage: [{ name: "lang", value: "de" }] }] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node e2e/start-backend.mjs",
      url: `http://localhost:${API_PORT}/api/health`,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `npm run build && npx vite preview --port ${PORT} --strictPort`,
      url: `http://localhost:${PORT}`,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
