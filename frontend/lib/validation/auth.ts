import { z } from "zod";

import {
  EXPERIENCE_LEVELS,
  RESUME_MAX_BYTES,
  RESUME_MIME_TYPES,
  TARGET_ROLES,
} from "@/lib/options";

// Client-side checks only. The backend must re-validate everything it receives.

const email = z.email("Enter a valid email address.");
const targetRole = z.enum(TARGET_ROLES, { error: "Select a target role." });
const graduationYear = z.string().min(1, "Select a graduation year.");
const experienceLevel = z.enum(EXPERIENCE_LEVELS, {
  error: "Select an experience level.",
});

export const loginSchema = z.object({
  email,
  password: z.string().min(1, "Enter your password."),
  remember: z.boolean(),
});
export type LoginValues = z.infer<typeof loginSchema>;

const password = z
  .string()
  .min(8, "Use at least 8 characters.")
  .max(128, "Use at most 128 characters.");

const passwordPair = z.object({ password, confirmPassword: z.string() });

export const signupSchema = z
  .object({
    fullName: z.string().trim().min(1, "Enter your full name.").max(100),
    email,
    password,
    confirmPassword: z.string(),
    targetRole,
    graduationYear,
    university: z.string().trim().min(1, "Enter your university.").max(150),
    experienceLevel,
    acceptTerms: z
      .boolean()
      .refine(Boolean, "Please accept the Terms of Service and Privacy Policy."),
  })
  .refine((v) => v.password === v.confirmPassword, {
    path: ["confirmPassword"],
    error: "Passwords don't match.",
    // Check as soon as the password itself is valid, not only once every field is.
    when: (payload) => passwordPair.safeParse(payload.value).success,
  });
export type SignupValues = z.infer<typeof signupSchema>;

export const onboardingSchema = z.object({
  targetRole,
  graduationYear,
  location: z.string().trim().min(1, "Enter a preferred location.").max(100),
  experienceLevel,
  resume: z
    .instanceof(File, { error: "Upload your résumé." })
    .refine((f) => RESUME_MIME_TYPES.includes(f.type), "Upload a PDF or DOCX file.")
    .refine((f) => f.size <= RESUME_MAX_BYTES, "File must be 10 MB or smaller."),
});
export type OnboardingValues = z.infer<typeof onboardingSchema>;
