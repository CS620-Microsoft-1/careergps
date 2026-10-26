"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { ComingSoon } from "@/components/common/coming-soon";
import { PasswordField, TextField } from "@/components/common/form-fields";
import { Button } from "@/components/ui/button";
import { FieldGroup } from "@/components/ui/field";
import { errorMessage } from "@/lib/api/client";
import { homeFor } from "@/lib/auth/account";
import { authErrorMessage } from "@/lib/auth/errors";
import { safeNextPath } from "@/lib/auth/next-path";
import { getSupabase } from "@/lib/supabase/client";
import { loginSchema, type LoginValues } from "@/lib/validation/auth";

export function LoginForm() {
  const router = useRouter();
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const [submitError, setSubmitError] = useState<string | null>(null);

  async function onSubmit(values: LoginValues) {
    setSubmitError(null);
    const { error } = await getSupabase().auth.signInWithPassword({
      email: values.email,
      password: values.password,
    });
    if (error) return setSubmitError(authErrorMessage(error));

    try {
      // Back to the page that sent them here (?next=, set by proxy.ts or a 401), except that
      // users who haven't finished onboarding go there first. Read at submit time so /login stays static.
      const next = safeNextPath(new URLSearchParams(window.location.search).get("next"));
      router.replace(await homeFor(next));
    } catch (accountError) {
      // Don't leave a session behind that the app can't use; the user can simply log in again.
      await getSupabase().auth.signOut({ scope: "local" }).catch(() => {});
      setSubmitError(errorMessage(accountError));
    }
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
          placeholder="Enter your password"
          autoComplete="current-password"
        />
        <div className="flex justify-end">
          <ComingSoon>
            <Button type="button" variant="link" disabled className="h-auto p-0">
              Forgot password?
            </Button>
          </ComingSoon>
        </div>
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
          {form.formState.isSubmitting ? "Signing in…" : "Sign In"}
        </Button>
      </FieldGroup>
      <p className="mt-6 text-center text-control text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link href="/signup" className="font-semibold text-primary hover:underline">
          Create Account
        </Link>
      </p>
    </form>
  );
}
