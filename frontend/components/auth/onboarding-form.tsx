"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronRight } from "lucide-react";
import { Controller, useForm } from "react-hook-form";

import { ResumeDropzone } from "@/components/auth/resume-dropzone";
import { TextField } from "@/components/common/form-fields";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldTitle } from "@/components/ui/field";
import { ApiError, errorMessage } from "@/lib/api/client";
import { updateProfile } from "@/lib/api/me";
import { uploadResume } from "@/lib/api/resumes";
import { onboardingSchema, type OnboardingValues } from "@/lib/validation/auth";

export function OnboardingForm() {
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string>();
  const form = useForm<OnboardingValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: { location: "" },
  });

  const onSubmit = async ({ location, resume }: OnboardingValues) => {
    setSubmitError(undefined);
    try {
      await updateProfile({ location });
      await uploadResume(resume);
    } catch (error) {
      // 409: a résumé is already uploaded (P0 allows one); its review page shows where it stands.
      if (!(error instanceof ApiError && error.status === 409)) {
        setSubmitError(errorMessage(error));
        return;
      }
    }
    router.push("/onboarding/review");
  };

  return (
    <form noValidate onSubmit={form.handleSubmit(onSubmit)}>
      <FieldGroup>
        <TextField
          control={form.control}
          name="location"
          label="Preferred Location"
          placeholder="United States"
          autoComplete="country-name"
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
        {submitError && (
          <p role="alert" className="text-control text-destructive">
            {submitError}
          </p>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? "Uploading…" : "Analyze My Career Profile"}
          <ChevronRight data-icon="inline-end" />
        </Button>
      </FieldGroup>
    </form>
  );
}
