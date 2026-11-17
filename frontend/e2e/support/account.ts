/**
 * A real Supabase test account, from E2E_EMAIL and E2E_PASSWORD (env vars or frontend/.env.e2e).
 * Its data comes from the mocked API, so it only needs to exist in Supabase with a confirmed email.
 * Without one, the signed-in tests are skipped.
 */
// Same env files as the app: Supabase settings, the API URL, and E2E_EMAIL / E2E_PASSWORD.
// The first file to set a variable wins, as with Next.js (.env.local over .env). Loaded here, not in
// playwright.config.ts: its imports run first, so this module would read the variables before they're set.
for (const file of [".env.e2e", ".env.local", ".env"]) {
  try { process.loadEnvFile(file); } catch { /* not every file exists */ }
}

export const account = { email: process.env.E2E_EMAIL ?? "", password: process.env.E2E_PASSWORD ?? "" };
export const hasAccount = Boolean(account.email && account.password);

/** The signed-in browser state the setup project saves and the signed-in tests start from. */
export const AUTH_FILE = "e2e/.auth/user.json";
