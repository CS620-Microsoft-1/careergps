"use client";

import { useRouter } from "next/navigation";

import { getSupabase } from "@/lib/supabase/client";

/**
 * Sign-out for /onboarding, which has no user menu. Without it, a student who signed up but
 * hasn't finished onboarding is sent back here from every page and can't reach /login.
 */
export function SignOutLink() {
  const router = useRouter();

  async function signOut() {
    await getSupabase().auth.signOut({ scope: "local" }).catch(() => {});
    router.replace("/login");
    router.refresh();
  }

  return (
    <p className="mt-6 text-center text-control text-muted-foreground">
      Wrong account?{" "}
      <button type="button" onClick={signOut} className="font-semibold text-primary hover:underline">
        Sign out
      </button>
    </p>
  );
}
