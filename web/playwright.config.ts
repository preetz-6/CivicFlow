import { defineConfig, devices } from "@playwright/test";

/**
 * One end-to-end test of the demo happy path (brief §14). It drives the real UI
 * against the real API, so the stack must be running:
 *   docker compose up -d   (db, api, web)   and   make demo   (fresh demo seed)
 * Point it elsewhere with E2E_BASE_URL (default http://localhost:5173).
 * Agents run in rules / replay mode for a deterministic result.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
