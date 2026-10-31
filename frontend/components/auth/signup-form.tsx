"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck } from "lucide-react";
import { Controller, useForm } from "react-hook-form";

import { AuthHeading } from "@/components/auth/auth-shell";
import { PasswordField, TextField } from "@/components/common/form-fields";
import { SetupStepper } from "@/components/setup/setup-shell";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldContent, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import type { SignupMetadata } from "@/lib/auth/account";
import { authErrorMessage } from "@/lib/auth/errors";
import { DEFAULT_UNIVERSITY } from "@/lib/options";
import { getSupabase } from "@/lib/supabase/client";
import { signupSchema, type SignupValues } from "@/lib/validation/auth";

const STEPS = ["Account", "School", "Verify"] as const;
/** Email domains we can name the school for. Anything else is typed in. */
const SCHOOL_DOMAINS: Record<string, string> = { "wisc.edu": DEFAULT_UNIVERSITY };

/**
 * Sign-up in three steps: 1 account, 2 school (for campus courses and clubs), 3 confirm the email.
 * The confirmation link is Supabase's; it lands on /auth/confirm, which continues to setup.
 */
export function SignupForm() {
  const router = useRouter();
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: { fullName: "", email: "", password: "", university: "", acceptTerms: false },
  });

  async function toSchool() {
    if (!(await form.trigger(["fullName", "email", "password"]))) return;
    if (!form.getValues("university")) {
      const domain = form.getValues("email").split("@")[1]?.toLowerCase() ?? "";
      const school = Object.entries(SCHOOL_DOMAINS).find(([key]) => domain === key || domain.endsWith(`.${key}`))?.[1];
      if (school) form.setValue("university", school);
    }
    setStep(1);
  }

  async function onSubmit(values: SignupValues) {
    setSubmitError(null);
    // Kept by Supabase; setup pre-fills from it and sends the consent with POST /me.
    const metadata: SignupMetadata = { accept_terms: true, full_name: values.fullName,
      ...(values.university ? { university: values.university } : {}) };
    const { data, error } = await getSupabase().auth.signUp({
      email: values.email,
      password: values.password,
      options: { data: metadata, emailRedirectTo: `${window.location.origin}/auth/confirm` },
    });
    if (error) return setSubmitError(authErrorMessage(error));
    // Only when email confirmation is turned off in Supabase: logged in right away.
    if (data.session && data.user) return router.push("/onboarding");
    // Same screen whether or not the email was already registered, so this form
    // can't be used to find out who has an account.
    setStep(2);
  }

  return (
    <>
      <SetupStepper current={step} steps={STEPS} label="Sign-up steps" className="mb-7" />
      {step === 2 ? (
        <div className="grid justify-items-center gap-3 text-center">
          <span aria-hidden className="grid size-14 place-items-center rounded-full bg-accent"><MailCheck className="size-6" /></span>
          <h1 className="text-[1.75rem]/9">Check your inbox</h1>
          <p className="text-muted-foreground">
            We sent a confirmation link to <b className="text-foreground">{form.getValues("email")}</b>. Open it on this
            device to verify your email and continue to setup.
          </p>
          <Button type="button" variant="ghost" className="mt-2" onClick={() => { form.setValue("password", ""); setStep(0); }}>
            Use a different email
          </Button>
        </div>
      ) : (
        <form noValidate onSubmit={form.handleSubmit(onSubmit)}>
          {step === 0 ? <>
            <AuthHeading title="Create your account" />
            <FieldGroup>
              <TextField control={form.control} name="fullName" label="Full name" autoComplete="name" />
              <TextField control={form.control} name="email" label="Email" type="email"
                placeholder="you@school.edu" autoComplete="email" />
              <PasswordField control={form.control} name="password" label="Password"
                placeholder="At least 8 characters" autoComplete="new-password" />
              <Button type="button" size="lg" className="w-full" onClick={() => void toSchool()}>Continue</Button>
            </FieldGroup>
          </> : <>
            <AuthHeading title="Confirm your school"
              subtitle="We use it to show courses and student orgs on your campus. Signing up with your school email confirms it." />
            <FieldGroup>
              <TextField control={form.control} name="university" label="School" placeholder={DEFAULT_UNIVERSITY}
                autoComplete="organization" />
              <Controller
                control={form.control}
                name="acceptTerms"
                render={({ field, fieldState }) => (
                  <Field orientation="horizontal" data-invalid={fieldState.invalid}>
                    <Checkbox id="acceptTerms" checked={field.value} onCheckedChange={(v) => field.onChange(v === true)}
                      aria-invalid={fieldState.invalid} />
                    <FieldContent>
                      <FieldLabel htmlFor="acceptTerms" className="font-normal">
                        I agree to the Terms of Service and Privacy Policy.
                      </FieldLabel>
                      <FieldError errors={[fieldState.error]} />
                    </FieldContent>
                  </Field>
                )}
              />
              {submitError && <p role="alert" className="text-sm text-destructive">{submitError}</p>}
              <Button type="submit" size="lg" className="w-full" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? "Creating account…" : "Create account"}
              </Button>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Button type="button" variant="ghost" disabled={form.formState.isSubmitting} onClick={() => setStep(0)}>Back</Button>
                <button type="button" className="text-sm font-bold underline disabled:opacity-60"
                  disabled={form.formState.isSubmitting}
                  onClick={() => { form.setValue("university", ""); void form.handleSubmit(onSubmit)(); }}>
                  I’m not a student right now
                </button>
              </div>
            </FieldGroup>
          </>}
        </form>
      )}
    </>
  );
}
