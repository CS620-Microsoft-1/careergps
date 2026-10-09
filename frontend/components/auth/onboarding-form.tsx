"use client";

import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronRight } from "lucide-react";
import { Controller, useForm } from "react-hook-form";

import { ResumeDropzone } from "@/components/auth/resume-dropzone";
import { SegmentedField, SelectField, TextField } from "@/components/common/form-fields";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldTitle } from "@/components/ui/field";
import { EXPERIENCE_LEVELS, TARGET_ROLES } from "@/lib/options";
import { onboardingSchema, type OnboardingValues } from "@/lib/validation/auth";

export function OnboardingForm({ graduationYears }: { graduationYears: string[] }) {
  const router = useRouter();
  const form = useForm<OnboardingValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: { graduationYear: "", location: "" },
  });

  // No backend yet: the résumé is not uploaded and nothing is analyzed.
  const onSubmit = () => router.push("/dashboard");

  return (
    <form noValidate onSubmit={form.handleSubmit(onSubmit)}>
      <FieldGroup>
        <SelectField
          control={form.control}
          name="targetRole"
          label="Target Role"
          placeholder="Select a role"
          options={TARGET_ROLES}
        />
        <div className="grid gap-4 @sm/field-group:grid-cols-2">
          <SelectField
            control={form.control}
            name="graduationYear"
            label="Graduation Year"
            placeholder="Select a year"
            options={graduationYears}
          />
          <TextField
            control={form.control}
            name="location"
            label="Preferred Location"
            placeholder="United States"
            autoComplete="country-name"
          />
        </div>
        <SegmentedField
          control={form.control}
          name="experienceLevel"
          label="Experience Level"
          options={EXPERIENCE_LEVELS}
        />
        <Controller
          control={form.control}
          name="resume"
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldTitle>Résumé</FieldTitle>
              <ResumeDropzone
                id="resume"
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
                invalid={fieldState.invalid}
              />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
        <Button type="submit" size="lg" className="w-full">
          Analyze My Career Profile
          <ChevronRight data-icon="inline-end" />
        </Button>
      </FieldGroup>
    </form>
  );
}
