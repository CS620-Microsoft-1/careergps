"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { getMe } from "@/lib/api/me";
import { getSupabase } from "@/lib/supabase/client";

/**
 * Sends users who haven't finished onboarding to /onboarding (SPEC-001 P2-2): their account row
 * is created at its end, so GET /me returns no user until then. It runs in the browser after the
 * page loads, so the page may show briefly first. /onboarding itself is outside
 * the app shell, so finished users can still go back there to upload a new résumé.
 */
export function OnboardingGuard() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    try {
      // Registers the access token for API calls; this effect can run before the user menu's.
      getSupabase();
    } catch {
      return; // Supabase isn't configured (UI-only development): nothing to check.
    }
    getMe()
      .then((me) => {
        if (!cancelled && !me.user) router.replace("/onboarding");
      })
      // API down or not logged in: leave the page alone (a 401 already goes to /login).
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [router]);

  return null;
}
