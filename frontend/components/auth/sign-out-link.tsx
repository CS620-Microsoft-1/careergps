"use client";

import { useRouter } from "next/navigation";

import { getSupabase } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

/**
 * Sign-out for the setup pages, which have no profile menu. Without it, a student who signed up but
 * hasn't finished setup is sent back here from every page and can't reach /login.
 */
export function SignOutLink({ className }: { className?: string }) {
  const router = useRouter();

  async function signOut() {
    await getSupabase().auth.signOut({ scope: "local" }).catch(() => {});
    router.replace("/login");
    router.refresh();
  }

  return (
    <button type="button" onClick={signOut} className={cn("text-sm font-bold hover:underline", className)}>
      Sign out
    </button>
  );
}
