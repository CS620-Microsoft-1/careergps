import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { setAccessTokenGetter } from "@/lib/api/client";
import { assertSupabaseConfig, SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/supabase/config";

let client: SupabaseClient | undefined;

/**
 * The browser's Supabase client. The session lives in cookies so proxy.ts can read it.
 * Creating it also makes every API call send the user's access token.
 */
export function getSupabase(): SupabaseClient {
  if (!client) {
    assertSupabaseConfig();
    const supabase = createBrowserClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
    setAccessTokenGetter(async () => {
      const { data } = await supabase.auth.getSession();
      return data.session?.access_token ?? null;
    });
    client = supabase;
  }
  return client;
}
