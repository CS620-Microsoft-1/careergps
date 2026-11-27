"use client";

import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck } from "lucide-react";
import { useForm } from "react-hook-form";

import { AuthHeading } from "@/components/auth/auth-shell";
import { TextField } from "@/components/common/form-fields";
import { Button } from "@/components/ui/button";
import { FieldGroup } from "@/components/ui/field";
import { authErrorMessage } from "@/lib/auth/errors";
import { getSupabase } from "@/lib/supabase/client";
import { forgotPasswordSchema, type ForgotPasswordValues } from "@/lib/validation/auth";

/** Supabase sends at most one email per address per minute by default. */
const RESEND_SECONDS = 60;

// Errors the student can act on. Anything else still shows "Check your inbox", so the form
// never reveals whether an email has an account.
const SHOWN_CODES = new Set(["over_email_send_rate_limit", "over_request_rate_limit", "email_address_invalid"]);

/**
 * Step one of a password reset: email a link that lands on /auth/reset
 * (docs/supabase/reset-password.html). Opened from /login, which may pass the typed email as ?email=.
 */
export function ForgotPasswordForm() {
  const form = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  // Read in the browser so the page stays static.
  useEffect(() => {
    const email = new URLSearchParams(window.location.search).get("email");
    if (email) form.setValue("email", email);
  }, [form]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((seconds) => seconds - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function onSubmit(values: ForgotPasswordValues) {
    setSubmitError(null);
    const { error } = await getSupabase().auth.resetPasswordForEmail(values.email, {
      redirectTo: `${window.location.origin}/auth/reset`,
    });
    const networkError = error && (error.status === 0 || error.name === "AuthRetryableFetchError");
    if (error && (networkError || SHOWN_CODES.has(error.code ?? ""))) {
      return setSubmitError(authErrorMessage(error));
    }
    setSentTo(values.email);
    setCooldown(RESEND_SECONDS);
  }

  if (sentTo) {
    const submitting = form.formState.isSubmitting;
    return (
      <div className="grid justify-items-center gap-3 text-center">
        <span aria-hidden className="grid size-14 place-items-center rounded-full bg-accent"><MailCheck className="size-6" /></span>
        <h1 className="text-[1.75rem]/9">Check your inbox</h1>
        <p className="text-muted-foreground">
          If an account exists for <b className="break-all text-foreground">{sentTo}</b>, we sent a link to reset your
          password. It can take a few minutes to arrive.
        </p>
        {submitError && <p role="alert" className="text-control text-destructive">{submitError}</p>}
        <div className="mt-2 flex flex-wrap justify-center gap-2">
          <Button type="button" variant="outline" disabled={cooldown > 0 || submitting}
            onClick={() => void form.handleSubmit(onSubmit)()}>
            {submitting ? "Sending…" : cooldown > 0 ? `Send again in ${cooldown}s` : "Send again"}
          </Button>
          <Button type="button" variant="ghost"
            onClick={() => { setSentTo(null); setSubmitError(null); }}>
            Use a different email
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form noValidate onSubmit={form.handleSubmit(onSubmit)}>
      <AuthHeading title="Reset your password" subtitle="Enter your account email and we’ll send you a link to choose a new password." />
      <FieldGroup>
        <TextField control={form.control} name="email" label="Email" type="email"
          placeholder="you@school.edu" autoComplete="email" />
        {submitError && <p role="alert" className="text-control text-destructive">{submitError}</p>}
        <Button type="submit" size="lg" className="w-full" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? "Sending…" : "Send reset link"}
        </Button>
      </FieldGroup>
    </form>
  );
}
