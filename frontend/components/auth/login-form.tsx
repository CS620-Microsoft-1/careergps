"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { ComingSoon } from "@/components/common/coming-soon";
import { TextField } from "@/components/common/form-fields";
import { Button } from "@/components/ui/button";
import { FieldGroup } from "@/components/ui/field";
import { errorMessage } from "@/lib/api/client";
import { ensureAccount } from "@/lib/auth/account";
import { authErrorMessage } from "@/lib/auth/errors";
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
    const { data, error } = await getSupabase().auth.signInWithPassword({
      email: values.email,
      password: values.password,
    });
    if (error) return setSubmitError(authErrorMessage(error));

    try {
      // First login after confirming by a link that didn't reach /auth/confirm: finish sign-up here.
      const { created } = await ensureAccount(data.user);
      router.replace(created ? "/onboarding" : "/dashboard");
    } catch (accountError) {
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
          placeholder="student@wisc.edu"
          autoComplete="email"
        />
        <TextField
          control={form.control}
          name="password"
          label="Password"
          type="password"
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
