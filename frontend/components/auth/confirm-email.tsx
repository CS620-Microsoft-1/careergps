"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2, MailCheck } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/client";
import { homeFor } from "@/lib/auth/account";
import { readConfirmLink, type TokenType } from "@/lib/auth/confirm-link";
import { authCodeMessage, authErrorMessage } from "@/lib/auth/errors";
import { getSupabase } from "@/lib/supabase/client";

type Progress = { step: "confirming" } | { step: "failed"; message: string } | null;

// The link never changes while the page is open, so there is nothing to subscribe to. On the server
// (prerender) there is no URL yet: null shows the spinner until the browser reads it.
const subscribe = () => () => {};
const readUrl = () => window.location.search + window.location.hash;
const noUrl = () => null;

/**
 * Where the email confirmation link lands (?token_hash=, from docs/supabase/confirm-signup.html).
 * The email is confirmed only when the student presses the button: mail scanners (such as
 * Microsoft 365 Safe Links on wisc.edu) open every link to check it, and the token is single-use,
 * so confirming on page load would let the scanner use it up first. Then on to onboarding.
 */
export function ConfirmEmail() {
  const router = useRouter();
  const url = useSyncExternalStore(subscribe, readUrl, noUrl);
  const [progress, setProgress] = useState<Progress>(null);

  async function confirm(tokenHash: string, type: TokenType) {
    setProgress({ step: "confirming" });
    const { error } = await getSupabase().auth.verifyOtp({ token_hash: tokenHash, type });
    if (error) return setProgress({ step: "failed", message: authErrorMessage(error) });
    try {
      router.replace(await homeFor(null));
    } catch (accountError) {
      setProgress({ step: "failed", message: errorMessage(accountError) });
    }
  }

  const hashAt = url?.indexOf("#") ?? -1;
  const link =
    url === null ? null : hashAt < 0 ? readConfirmLink(url, "") : readConfirmLink(url.slice(0, hashAt), url.slice(hashAt));
  const failure =
    progress?.step === "failed" ? progress.message : link?.kind === "error" ? authCodeMessage(link.code) : null;

  if (failure) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="We couldn't finish signing you in"
        description={failure}
        action={
          <Button asChild>
            <Link href="/login">Go to Sign In</Link>
          </Button>
        }
      />
    );
  }

  if (link?.kind === "token" && progress === null) {
    return (
      <EmptyState
        icon={MailCheck}
        title="Confirm your email"
        description="Press the button to confirm your email and continue to CareerGPS."
        action={
          <Button size="lg" onClick={() => confirm(link.tokenHash, link.type)}>
            Confirm my email
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
