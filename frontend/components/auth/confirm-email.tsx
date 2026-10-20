"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2 } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/client";
import { homeFor } from "@/lib/auth/account";
import { authCodeMessage } from "@/lib/auth/errors";
import { getSupabase } from "@/lib/supabase/client";

/**
 * Where the email confirmation link lands. Supabase has already confirmed the email by now;
 * this turns the link's code into a session and moves on to onboarding (or the dashboard, for an
 * account that has already finished it).
 */
export function ConfirmEmail() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function confirm() {
      // Supabase reports a bad or expired link in the URL instead of a code.
      const params = new URLSearchParams(window.location.search + window.location.hash.replace("#", "&"));
      if (params.has("error_code")) return setError(authCodeMessage(params.get("error_code")));

      // The client exchanges ?code= for a session while it initializes. That needs the
      // browser the user signed up in; anywhere else there is no session, only a confirmed email.
      const supabase = getSupabase();
      await supabase.auth.initialize();
      const { data } = await supabase.auth.getUser();
      if (cancelled) return;
      if (!data.user) {
        return setError("Your email is confirmed. Sign in to continue.");
      }

      try {
        const home = await homeFor(null);
        if (!cancelled) router.replace(home);
      } catch (accountError) {
        if (!cancelled) setError(errorMessage(accountError));
      }
    }

    confirm();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="We couldn't finish signing you in"
        description={error}
        action={
          <Button asChild>
            <Link href="/login">Go to Sign In</Link>
          </Button>
        }
      />
    );
  }

  return (
    <div role="status" className="grid justify-items-center gap-2 py-16 text-center">
      <Loader2 aria-hidden className="size-6 animate-spin text-primary" />
      <p className="font-semibold">Confirming your email…</p>
    </div>
  );
}
