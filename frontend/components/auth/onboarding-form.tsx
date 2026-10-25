"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronRight } from "lucide-react";
import { Controller, useForm } from "react-hook-form";

import { ResumeDropzone } from "@/components/auth/resume-dropzone";
import { ResumeReview } from "@/components/onboarding/resume-review";
import { SegmentedField, SelectField, TextField } from "@/components/common/form-fields";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldTitle } from "@/components/ui/field";
import { EXPERIENCE_LEVELS, TARGET_ROLES } from "@/lib/options";
import { analyzeResume } from "@/lib/api/resumes";
import { ApiError } from "@/lib/api/client";
import { onboardingSchema, type OnboardingValues } from "@/lib/validation/auth";
import type { ResumeAnalysis, ResumeClassification } from "@/types/api";
import { clearConfirmedResume, loadConfirmedResume, queueSkillGapAnalysis, saveConfirmedResume } from "@/lib/confirmed-resume";

export function OnboardingForm({ graduationYears }: { graduationYears: string[] }) {
  const router = useRouter();
  const [analysis, setAnalysis] = useState<ResumeAnalysis>();
  const [classification, setClassification] = useState<ResumeClassification>();
  const [submitError, setSubmitError] = useState<string>();
  const [confirming, setConfirming] = useState(false);
  const form = useForm<OnboardingValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: { graduationYear: "", location: "" },
  });
  const { setValue } = form;

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (new URLSearchParams(window.location.search).get("edit") !== "1") return;
      try {
        const snapshot = loadConfirmedResume();
        if (!snapshot) return;
        setAnalysis(snapshot.analysis);
        setClassification(snapshot.reviewed_resume);
        setValue("targetRole", snapshot.onboarding.targetRole);
        setValue("graduationYear", snapshot.onboarding.graduationYear);
        setValue("location", snapshot.onboarding.location);
        setValue("experienceLevel", snapshot.onboarding.experienceLevel);
      } catch {
        setSubmitError("This browser could not restore the local résumé. Upload it again.");
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [setValue]);

  const onSubmit = async ({ resume }: OnboardingValues) => {
    setSubmitError(undefined);
    try {
      const result = await analyzeResume(resume);
      setAnalysis(result);
      setClassification(result.classification);
    } catch (error) {
      if (error instanceof ApiError) {
        setSubmitError(error.detail ?? error.message);
      } else {
        setSubmitError("Something went wrong while reading the résumé.");
      }
    }
  };

  if (analysis && classification) {
    return (
      <ResumeReview
        result={analysis}
        classification={classification}
        onChange={setClassification}
        onStartOver={() => {
          clearConfirmedResume();
          setAnalysis(undefined);
          setClassification(undefined);
          setSubmitError(undefined);
          form.resetField("resume");
        }}
        confirming={confirming}
        confirmError={submitError}
        onConfirm={async () => {
          if (confirming) return;
          setConfirming(true);
          setSubmitError(undefined);
          try {
            const values = form.getValues();
            const snapshot = await saveConfirmedResume(analysis, classification, {
              targetRole: values.targetRole,
              graduationYear: values.graduationYear,
              location: values.location,
              experienceLevel: values.experienceLevel,
            });
            queueSkillGapAnalysis(snapshot);
            router.push("/dashboard");
          } catch {
            setSubmitError("Your résumé could not be kept in this browser tab. Allow local browser storage and try again.");
          } finally {
            setConfirming(false);
          }
        }}
      />
    );
  }

  return (
    <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="mx-auto max-w-100">
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
          {form.formState.isSubmitting ? "Reading résumé…" : "Analyze My Career Profile"}
          <ChevronRight data-icon="inline-end" />
        </Button>
      </FieldGroup>
    </form>
  );
}
