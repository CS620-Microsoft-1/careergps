"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";

import { SegmentedField, SelectField, TextField } from "@/components/common/form-fields";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldContent, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  DEFAULT_UNIVERSITY,
  EXPERIENCE_LEVELS,
  TARGET_ROLES,
} from "@/lib/options";
import { signupSchema, type SignupValues } from "@/lib/validation/auth";

/** Two fields side by side when the form is wide enough, stacked otherwise. */
function FieldRow({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-4 @sm/field-group:grid-cols-2">{children}</div>;
}

export function SignupForm({ graduationYears }: { graduationYears: string[] }) {
  const router = useRouter();
  const form = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      fullName: "",
      email: "",
      password: "",
      confirmPassword: "",
      graduationYear: "",
      university: DEFAULT_UNIVERSITY,
      acceptTerms: false,
    },
  });

  // No backend yet: a valid form simply continues to onboarding.
  const onSubmit = () => router.push("/onboarding");

  return (
    <form noValidate onSubmit={form.handleSubmit(onSubmit)}>
      <FieldGroup>
        <TextField
          control={form.control}
          name="fullName"
          label="Full Name"
          placeholder="Your full name"
          autoComplete="name"
        />
        <TextField
          control={form.control}
          name="email"
          label="University Email"
          type="email"
          placeholder="student@wisc.edu"
          autoComplete="email"
        />
        <FieldRow>
          <TextField
            control={form.control}
            name="password"
            label="Password"
            type="password"
            placeholder="At least 8 characters"
            autoComplete="new-password"
          />
          <TextField
            control={form.control}
            name="confirmPassword"
            label="Confirm Password"
            type="password"
            autoComplete="new-password"
          />
        </FieldRow>
        <FieldRow>
          <SelectField
            control={form.control}
            name="targetRole"
            label="Target Role"
            placeholder="Select a role"
            options={TARGET_ROLES}
          />
          <SelectField
            control={form.control}
            name="graduationYear"
            label="Graduation Year"
            placeholder="Select a year"
            options={graduationYears}
          />
        </FieldRow>
        <TextField
          control={form.control}
          name="university"
          label="University"
          autoComplete="organization"
        />
        <SegmentedField
          control={form.control}
          name="experienceLevel"
          label="Experience Level"
          options={EXPERIENCE_LEVELS}
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
        <Button type="submit" size="lg" className="w-full">
          Create Account
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
