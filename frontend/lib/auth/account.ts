import type { User as SupabaseUser } from "@supabase/supabase-js";

import { getMe } from "@/lib/api/me";

/** What signUp() saves in Supabase user_metadata, read back when onboarding finishes. */
export type SignupMetadata = { accept_terms: true };

/**
 * Where a logged-in user goes next: /onboarding until it is finished (the account row is created
 * at its end), otherwise `next` or the dashboard.
 */
export async function homeFor(next: string | null): Promise<string> {
  const { user } = await getMe();
  return user ? (next ?? "/dashboard") : "/onboarding";
}

/** The terms consent given at sign-up; the API rejects anything but true. */
export function acceptedTerms(user: SupabaseUser): true {
  return (user.user_metadata as Partial<SignupMetadata>).accept_terms as true;
}
