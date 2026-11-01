"use client";

import { getSupabase } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

/**
 * Sign-out for the setup pages, which have no profile menu. Without it, a student who signed up but
 * hasn't finished setup is sent back here from every page and can't reach /login.
 */
export function SignOutLink({ className }: { className?: string }) {
  async function signOut() {
    await getSupabase().auth.signOut({ scope: "local" }).catch(() => {});
    // A full page load, so no hidden page keeps this user's state for the next one.
    window.location.replace("/login");
  }

  return (
    <button type="button" onClick={signOut} className={cn("text-sm font-bold hover:underline", className)}>
      Sign out
    </button>
  );
}
