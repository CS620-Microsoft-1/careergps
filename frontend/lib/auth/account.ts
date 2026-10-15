import type { User as SupabaseUser } from "@supabase/supabase-js";

import { ApiError } from "@/lib/api/client";
import { createAccount, getMe } from "@/lib/api/me";
import type { AccountCreateRequest, MeResponse } from "@/types/api";

/** What signUp() saves in Supabase user_metadata, read back after confirmation. */
export type SignupMetadata = AccountCreateRequest;

/**
 * Makes sure the logged-in user has their users + profiles rows (POST /me), creating them the
 * first time with the terms consent given at sign-up. Called after email confirmation and after every login, so
 * it also works when the confirmation link didn't reach /auth/confirm.
 * `created` is true when this call finished sign-up.
 */
export async function ensureAccount(user: SupabaseUser): Promise<{ me: MeResponse; created: boolean }> {
  const me = await getMe();
  if (me.user) return { me, created: false };

  const data = user.user_metadata as Partial<SignupMetadata>;
  try {
    // Only what the user actually accepted at sign-up; the API rejects anything but true.
    const created = await createAccount({ accept_terms: data.accept_terms as true });
    return { me: created, created: true };
  } catch (error) {
    // Another tab finished sign-up first.
    if (error instanceof ApiError && error.status === 409) return { me: await getMe(), created: false };
    throw error;
  }
}
