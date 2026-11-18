import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { setAuthSessionGetter } from "@/lib/api/client";
import { assertSupabaseConfig, SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/supabase/config";

let client: SupabaseClient | undefined;
/**
 * The browser's Supabase client. The session lives in cookies so proxy.ts can read it.
 * Creating it also makes every API call use the token and owner from the same session.
 * API errors leave the shared session intact; signing out remains an explicit user action.
 */
export function getSupabase(): SupabaseClient {
  if (!client) {
    assertSupabaseConfig();
    const supabase = createBrowserClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
    setAuthSessionGetter(async () => {
      const { data } = await supabase.auth.getSession();
      return { accessToken: data.session?.access_token ?? null, userId: data.session?.user.id ?? null };
    });
    client = supabase;
  }
  return client;
}
