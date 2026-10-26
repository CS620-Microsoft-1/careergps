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
import { DEFAULT_UNIVERSITY, EXPERIENCE_LEVELS, TARGET_ROLES } from "@/lib/options";
import { analyzeResume } from "@/lib/api/resumes";
import { ApiError, errorMessage } from "@/lib/api/client";
import { addResume, createAccount, getMe, getSavedResume, updateAccount } from "@/lib/api/me";
import { acceptedTerms } from "@/lib/auth/account";
import { getSupabase } from "@/lib/supabase/client";
import { onboardingSchema, type OnboardingValues } from "@/lib/validation/auth";
import { profileForAnalysis, queueSkillGapAnalysis } from "@/lib/skill-gap-profile";
import type { ResumeAnalysis, ResumeClassification } from "@/types/api";

export function OnboardingForm({ graduationYears }: { graduationYears: string[] }) {
  const router = useRouter();
  const [analysis, setAnalysis] = useState<ResumeAnalysis>();
  const [classification, setClassification] = useState<ResumeClassification>();
  const [submitError, setSubmitError] = useState<string>();
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string>();
  const [university, setUniversity] = useState("");
  // A returning student's saved university, used when the new résumé lists no school.
  const [savedUniversity, setSavedUniversity] = useState<string>();
  const form = useForm<OnboardingValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: { firstName: "", lastName: "", graduationYear: "", location: "" },
  });

  // Back from the profile page with a new résumé: start from what the account already has.
  useEffect(() => {
    let cancelled = false;
    getMe()
      .then(({ user }) => {
        if (cancelled || !user) return;
        setSavedUniversity(user.university);
        if (form.formState.isDirty) return;
        const year = String(user.graduation_year);
        form.reset({
          firstName: user.first_name,
          lastName: user.last_name,
          targetRole: user.target_role as OnboardingValues["targetRole"],
          experienceLevel: user.experience_level as OnboardingValues["experienceLevel"],
          graduationYear: graduationYears.includes(year) ? year : "",
          location: user.preferred_location,
        });
      })
      .catch(() => {}); // A new user, or the API is down: the form simply starts empty.
    return () => {
      cancelled = true;
    };
  }, [form, graduationYears]);

  const onSubmit = async ({ resume }: OnboardingValues) => {
    setSubmitError(undefined);
    try {
      const result = await analyzeResume(resume);
      setAnalysis(result);
      setClassification(result.classification);
      setUniversity(firstSchool(result.classification) ?? savedUniversity ?? DEFAULT_UNIVERSITY);
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
          setAnalysis(undefined);
          setClassification(undefined);
          form.resetField("resume");
        }}
        confirming={confirming}
        confirmError={confirmError}
        university={university}
        onUniversityChange={setUniversity}
        onConfirm={async () => {
          const { firstName, lastName, targetRole, experienceLevel, graduationYear, location } =
            form.getValues();
          if (!university.trim()) {
            setConfirmError("Enter your university.");
            return;
          }
          const details = { first_name: firstName, last_name: lastName, university: university.trim() };
          const goals = {
            target_role: targetRole,
            experience_level: experienceLevel,
            graduation_year: Number(graduationYear),
            preferred_location: location,
          };
          const resume = {
            original_filename: analysis.filename,
            parser: analysis.extraction.parser,
            ocr_pages: analysis.extraction.ocr_pages,
            agent_name: analysis.agent.name,
            classification,
          };
          setConfirming(true);
          setConfirmError(undefined);
          try {
            const { user } = await getMe();
            if (user) {
              // Back from the profile page with a new résumé: update the account, add a résumé version.
              await Promise.all([updateAccount({ ...details, ...goals }), addResume(resume)]);
            } else {
              // First time: this creates the account, with the terms consent given at sign-up.
              const { data } = await getSupabase().auth.getUser();
              if (!data.user) throw new Error("Not logged in");
              await createAccount({ ...details, ...goals, accept_terms: acceptedTerms(data.user), resume });
            }
          } catch (error) {
            setConfirmError(errorMessage(error, "Couldn't save your profile. Try again."));
            setConfirming(false);
            return;
          }
          // Persist first; the dashboard can then analyze the saved résumé by ID.
          try {
            const [{ user }, savedResume] = await Promise.all([getMe(), getSavedResume()]);
            if (user && savedResume) queueSkillGapAnalysis(profileForAnalysis(user, savedResume));
          } catch { /* Saving succeeded; analysis remains available explicitly if reload fails. */ }
          router.push("/dashboard");
        }}
      />
    );
  }

  return (
    <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="mx-auto max-w-100">
      <FieldGroup>
        <div className="grid gap-4 @sm/field-group:grid-cols-2">
          <TextField
            control={form.control}
            name="firstName"
            label="First Name"
            placeholder="Ada"
            autoComplete="given-name"
          />
          <TextField
            control={form.control}
            name="lastName"
            label="Last Name"
            placeholder="Lovelace"
            autoComplete="family-name"
          />
        </div>
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

/** The first school listed in the résumé's education, to pre-fill the University field. */
function firstSchool(classification: ResumeClassification): string | undefined {
  for (const entry of classification.education) {
    const name = typeof entry.institution === "string" ? entry.institution.trim() : "";
    if (name) return name.slice(0, 150);
  }
  return undefined;
}
