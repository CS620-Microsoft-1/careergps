import { defineConfig, devices } from "@playwright/test";

import { AUTH_FILE } from "./e2e/support/account";

// Same env files as the app: Supabase settings, the API URL, and E2E_EMAIL / E2E_PASSWORD.
// The first file to set a variable wins, as with Next.js (.env.local over .env).
for (const file of [".env.e2e", ".env.local", ".env"]) {
  try { process.loadEnvFile(file); } catch { /* not every file exists */ }
}

const BASE_URL = "http://localhost:3000";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: BASE_URL, trace: "on-first-retry" },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    { name: "signed-out", testMatch: /public\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "signed-in",
      testMatch: /signed-in\/.*\.spec\.ts/,
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], storageState: AUTH_FILE },
    },
  ],
  // Production build, as the Next.js guide recommends. A server already on :3000 (npm run dev) is reused locally.
  webServer: {
    command: "npm run build && npm run start",
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 300_000,
  },
});
