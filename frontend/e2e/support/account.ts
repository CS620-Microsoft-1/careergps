/**
 * A real Supabase test account, from E2E_EMAIL and E2E_PASSWORD (env vars or frontend/.env.e2e).
 * Its data comes from the mocked API, so it only needs to exist in Supabase with a confirmed email.
 * Without one, the signed-in tests are skipped.
 */
export const account = { email: process.env.E2E_EMAIL ?? "", password: process.env.E2E_PASSWORD ?? "" };
export const hasAccount = Boolean(account.email && account.password);

/** The signed-in browser state the setup project saves and the signed-in tests start from. */
export const AUTH_FILE = "e2e/.auth/user.json";
