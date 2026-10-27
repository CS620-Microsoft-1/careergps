"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2 } from "lucide-react";

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
 * The email is confirmed as soon as the page runs in the browser, then on to onboarding. Mail
 * scanners (such as Microsoft 365 Safe Links on wisc.edu) that run scripts can use the single-use
 * token first; the email is confirmed then too, so the failure screen sends the student to log in.
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

  // Once per page: the token is single-use, and development mode runs effects twice.
  const started = useRef(false);
  useEffect(() => {
    if (link?.kind !== "token" || started.current) return;
    started.current = true;
    void confirm(link.tokenHash, link.type);
  });

  if (failure) {
    return (
      <div className="grid justify-items-center gap-3 text-center">
        <span aria-hidden className="grid size-14 place-items-center rounded-full bg-danger-soft"><AlertTriangle className="size-6" /></span>
        <h1 className="text-[1.75rem]/9">We couldn’t verify you</h1>
        <p className="text-muted-foreground">{failure}</p>
        <Button asChild size="lg" className="mt-2"><Link href="/login">Go to log in</Link></Button>
      </div>
    );
  }

  return (
    <div role="status" className="grid justify-items-center gap-2 py-16 text-center">
      <Loader2 aria-hidden className="size-6 animate-spin" />
      <p className="font-bold">Verifying your email…</p>
    </div>
  );
}
