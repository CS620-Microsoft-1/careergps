import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { setAccessTokenGetter, setUnauthorizedHandler } from "@/lib/api/client";
import { loginPath } from "@/lib/auth/next-path";
import { assertSupabaseConfig, SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/supabase/config";

let client: SupabaseClient | undefined;
let leaving = false;

const AUTH_PAGES = ["/login", "/signup", "/auth"];

/**
 * The browser's Supabase client. The session lives in cookies so proxy.ts can read it.
 * Creating it also makes every API call send the user's access token, and sends the user to
 * /login when the API rejects it.
 */
export function getSupabase(): SupabaseClient {
  if (!client) {
    assertSupabaseConfig();
    const supabase = createBrowserClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
    setAccessTokenGetter(async () => {
      const { data } = await supabase.auth.getSession();
      return data.session?.access_token ?? null;
    });
    setUnauthorizedHandler(() => {
      const { pathname, search } = window.location;
      // Login and sign-up show their own errors; redirecting there would hide them.
      if (leaving || AUTH_PAGES.some((path) => pathname === path || pathname.startsWith(`${path}/`))) return;
      leaving = true;
      // Drop the session first: proxy.ts would otherwise still see a login and bounce back.
      void supabase.auth
        .signOut({ scope: "local" })
        .finally(() => window.location.replace(loginPath(pathname + search)));
    });
    client = supabase;
  }
  return client;
}
