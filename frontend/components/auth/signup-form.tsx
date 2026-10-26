"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck } from "lucide-react";
import { Controller, useForm } from "react-hook-form";

import { EmptyState } from "@/components/common/empty-state";
import { PasswordField, TextField } from "@/components/common/form-fields";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldContent, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { authErrorMessage } from "@/lib/auth/errors";
import type { SignupMetadata } from "@/lib/auth/account";
import { getSupabase } from "@/lib/supabase/client";
import { signupSchema, type SignupValues } from "@/lib/validation/auth";

export function SignupForm() {
  const router = useRouter();
  const form = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: { email: "", password: "", confirmPassword: "", acceptTerms: false },
  });

  const [submitError, setSubmitError] = useState<string | null>(null);
  // Set once Supabase has emailed the confirmation link.
  const [sentTo, setSentTo] = useState<string | null>(null);

  async function onSubmit(values: SignupValues) {
    setSubmitError(null);
    // Kept by Supabase until the email is confirmed; /auth/confirm then sends it to POST /me.
    const metadata: SignupMetadata = { accept_terms: true };
    const { data, error } = await getSupabase().auth.signUp({
      email: values.email,
      password: values.password,
      options: { data: metadata, emailRedirectTo: `${window.location.origin}/auth/confirm` },
    });
    if (error) return setSubmitError(authErrorMessage(error));

    // Only when email confirmation is turned off in Supabase: logged in right away.
    if (data.session && data.user) {
      // Email confirmation is off: logged in straight away. The account is created at the end of onboarding.
      return router.push("/onboarding");
    }
    // Same message whether or not the email was already registered, so this form
    // can't be used to find out who has an account.
    setSentTo(values.email);
  }

  if (sentTo) {
    return (
      <EmptyState
        icon={MailCheck}
        title="Check your email"
        description={`We sent a confirmation link to ${sentTo}. Open it on this device to finish creating your account.`}
        action={
          <Button variant="outline" asChild>
            <Link href="/login">Back to Sign In</Link>
          </Button>
        }
      />
    );
  }

  return (
    <form noValidate onSubmit={form.handleSubmit(onSubmit)}>
      <FieldGroup>
        <TextField
          control={form.control}
          name="email"
          label="Email"
          type="email"
          placeholder="you@example.com"
          autoComplete="email"
        />
        <PasswordField
          control={form.control}
          name="password"
          label="Password"
          placeholder="At least 8 characters"
          autoComplete="new-password"
        />
        <PasswordField
          control={form.control}
          name="confirmPassword"
          label="Confirm Password"
          placeholder="Type it again"
          autoComplete="new-password"
        />
        <Controller
          control={form.control}
          name="acceptTerms"
          render={({ field, fieldState }) => (
            <Field orientation="horizontal" data-invalid={fieldState.invalid}>
              <Checkbox
                id="acceptTerms"
                checked={field.value}
                onCheckedChange={(v) => field.onChange(v === true)}
                aria-invalid={fieldState.invalid}
              />
              <FieldContent>
                <FieldLabel htmlFor="acceptTerms" className="font-normal">
                  I agree to the Terms of Service and Privacy Policy.
                </FieldLabel>
                <FieldError errors={[fieldState.error]} />
              </FieldContent>
            </Field>
          )}
        />
        {submitError && (
          <p role="alert" className="text-control text-destructive">
            {submitError}
          </p>
        )}
        <Button
          type="submit"
          size="lg"
          className="w-full"
          disabled={form.formState.isSubmitting}
        >
          {form.formState.isSubmitting ? "Creating account…" : "Create Account"}
        </Button>
      </FieldGroup>
      <p className="mt-6 text-center text-control text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-primary hover:underline">
          Sign In
        </Link>
      </p>
    </form>
  );
}
