// Starts the backend for the end-to-end tests: fresh SQLite DB, migrations, demo data, then uvicorn.
// Platform independent (Node) so the run is the same on Linux (CI) and Windows.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { E2E_ADMIN } from "./helpers/credentials.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const backend = resolve(here, "../../backend");
const dataDir = resolve(here, "../.e2e");
const dbFile = resolve(dataDir, "e2e.db");
const python = process.env.E2E_PYTHON ?? (existsSync(resolve(backend, ".venv/bin/python")) ? resolve(backend, ".venv/bin/python") : "python");

mkdirSync(dataDir, { recursive: true });
for (const f of [dbFile, `${dbFile}-wal`, `${dbFile}-shm`]) rmSync(f, { force: true });

const env = {
  ...process.env,
  DATABASE_URL: `sqlite:///${dbFile.replaceAll("\\", "/")}`,
  DEMO_MODE: "true",
  ADMIN_EMAIL: E2E_ADMIN.email,
  ADMIN_PASSWORD: E2E_ADMIN.password,
  SESSION_SECRET: "e2e-only-secret-not-for-production-use-0123456789",
  // Do not pass on keys from the environment: the tests must never contact real providers.
  YAHOO_ENABLED: "false",
  // Hermetic: all outgoing traffic (GDELT status fetch, OpenFIGI search, ...) goes nowhere and fails immediately as a
  // source error. The tests must never reach real providers, not even without a key.
  HTTP_PROXY: "http://127.0.0.1:9", HTTPS_PROXY: "http://127.0.0.1:9", ALL_PROXY: "http://127.0.0.1:9",
  http_proxy: "http://127.0.0.1:9", https_proxy: "http://127.0.0.1:9", all_proxy: "http://127.0.0.1:9",
  NO_PROXY: "127.0.0.1,localhost", no_proxy: "127.0.0.1,localhost",
  ...Object.fromEntries(["FINNHUB_API_KEY", "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY", "STOOQ_API_KEY", "OPENFIGI_API_KEY",
    "MARKETAUX_API_KEY", "ALPHAVANTAGE_API_KEY", "ANTHROPIC_API_KEY", "SEC_EDGAR_CONTACT_EMAIL", "RSS_ENABLED_FEEDS",
    "EQS_RSS_URL", "IR_FEEDS"].map((k) => [k, ""])),
};

function run(args) {
  const r = spawnSync(python, args, { cwd: backend, env, stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status ?? 1);
}

run(["-m", "alembic", "upgrade", "head"]);
run(["-m", "app.e2e_seed"]);

const api = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], { cwd: backend, env, stdio: "inherit" });
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => api.kill());
api.on("exit", (code) => process.exit(code ?? 0));
