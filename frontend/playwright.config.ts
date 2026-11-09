import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests: real pages in a headless browser, API answered by e2e/mock-api.ts.
 * No backend, no Supabase, no Agent call. Local only; not part of CI (see README "End-to-end tests").
 *
 * The dev server starts with the Supabase variables empty, so the pages skip login, and with the
 * API URL pointing at a path on the same origin that page.route() intercepts.
 */
const PORT = 3102;
const BASE_URL = `http://localhost:${PORT}`;
export const API_PREFIX = "/api-mock";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: 3,
  retries: 0,
  reporter: "list",
  timeout: 30_000,
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npx next dev -p ${PORT}`,
    url: `${BASE_URL}/resources`,
    // Fails fast when something else holds the port, instead of testing a server we don't control.
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_SUPABASE_URL: "",
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "",
      NEXT_PUBLIC_API_URL: `${BASE_URL}${API_PREFIX}`,
    },
  },
});
