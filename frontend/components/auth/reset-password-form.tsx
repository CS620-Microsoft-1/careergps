"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { useForm } from "react-hook-form";

import { AuthHeading } from "@/components/auth/auth-shell";
import { PasswordField } from "@/components/common/form-fields";
import { Button } from "@/components/ui/button";
import { FieldGroup } from "@/components/ui/field";
import { errorMessage } from "@/lib/api/client";
import { homeFor } from "@/lib/auth/account";
import { readRecoveryLink } from "@/lib/auth/confirm-link";
import { recoveryCodeMessage, recoveryErrorMessage } from "@/lib/auth/errors";
import { getSupabase } from "@/lib/supabase/client";
import { resetPasswordSchema, type ResetPasswordValues } from "@/lib/validation/auth";

// Only these verifyOtp failures mean the link itself is dead; anything else (e.g. no network)
// may not have spent the token, so the student can simply submit again.
const DEAD_LINK_CODES = new Set(["otp_expired", "flow_state_expired", "otp_disabled", "bad_jwt"]);

type Outcome =
  /** The link can't be used: show why and offer a new one. */
  | { kind: "dead"; message: string }
  /** The password changed, but loading the account failed. */
  | { kind: "saved"; message: string }
  | null;

// The link never changes while the page is open. On the server (prerender) there is no URL yet.
const subscribe = () => () => {};
const readUrl = () => window.location.search + window.location.hash;
const noUrl = () => null;

/**
 * Where the password reset email lands (?token_hash=…&type=recovery, from
 * docs/supabase/reset-password.html). The token is spent only when the student submits a new
 * password, never on page load, so a mail scanner that opens the link can't use it up first.
 */
export function ResetPasswordForm() {
  const router = useRouter();
  const url = useSyncExternalStore(subscribe, readUrl, noUrl);
  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "", confirmPassword: "" },
  });
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // The token is single-use: once verified, a retry (e.g. after same_password) only saves the password.
  const [verified, setVerified] = useState(false);

  const hashAt = url?.indexOf("#") ?? -1;
  const link =
    url === null ? null : hashAt < 0 ? readRecoveryLink(url, "") : readRecoveryLink(url.slice(0, hashAt), url.slice(hashAt));

  async function onSubmit(values: ResetPasswordValues) {
    if (link?.kind !== "token") return;
    setSubmitError(null);
    const auth = getSupabase().auth;

    if (!verified) {
      const { error } = await auth.verifyOtp({ token_hash: link.tokenHash, type: "recovery" });
      if (error) {
        if (DEAD_LINK_CODES.has(error.code ?? "")) {
          return setOutcome({ kind: "dead", message: recoveryErrorMessage(error) });
        }
        return setSubmitError(recoveryErrorMessage(error));
      }
      setVerified(true);
    }

    const { error } = await auth.updateUser({ password: values.password });
    if (error) return setSubmitError(recoveryErrorMessage(error));

    // Someone who knew the old password may still be logged in elsewhere. The reset is done
    // either way, so a failure here doesn't stop the student.
    await auth.signOut({ scope: "others" }).catch(() => {});

    try {
      router.replace(await homeFor(null));
    } catch (accountError) {
      setOutcome({ kind: "saved", message: errorMessage(accountError) });
    }
  }

  if (url === null) {
    return (
      <div role="status" className="grid justify-items-center gap-2 py-16 text-center">
        <Loader2 aria-hidden className="size-6 animate-spin" />
        <p className="font-bold">Checking your link…</p>
      </div>
    );
  }

  const dead = outcome?.kind === "dead" ? outcome.message : link?.kind === "error" ? recoveryCodeMessage(link.code) : null;
  if (dead) {
    return (
      <div className="grid justify-items-center gap-3 text-center">
        <span aria-hidden className="grid size-14 place-items-center rounded-full bg-danger-soft"><AlertTriangle className="size-6" /></span>
        <h1 className="text-[1.75rem]/9">This link can’t be used</h1>
        <p className="text-muted-foreground">{dead}</p>
        <Button asChild size="lg" className="mt-2"><Link href="/forgot-password">Request a new link</Link></Button>
      </div>
    );
  }

  if (outcome?.kind === "saved") {
    return (
      <div className="grid justify-items-center gap-3 text-center">
        <span aria-hidden className="grid size-14 place-items-center rounded-full bg-accent"><CheckCircle2 className="size-6" /></span>
        <h1 className="text-[1.75rem]/9">Password updated</h1>
        <p className="text-muted-foreground">{outcome.message}</p>
        <Button asChild size="lg" className="mt-2"><Link href="/login">Go to log in</Link></Button>
      </div>
    );
  }

  const submitting = form.formState.isSubmitting;
  return (
    <form noValidate onSubmit={form.handleSubmit(onSubmit)}>
      <AuthHeading title="Choose a new password" />
      <FieldGroup>
        <PasswordField control={form.control} name="password" label="New password"
          placeholder="At least 8 characters" autoComplete="new-password" />
        <PasswordField control={form.control} name="confirmPassword" label="Confirm password"
          autoComplete="new-password" />
        {submitError && <p role="alert" className="text-control text-destructive">{submitError}</p>}
        <Button type="submit" size="lg" className="w-full" disabled={submitting}>
          {submitting ? "Saving…" : "Save password"}
        </Button>
      </FieldGroup>
    </form>
  );
}
