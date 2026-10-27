import { z } from "zod";

// Client-side checks only. The backend must re-validate everything it receives.

const email = z.email("Enter a valid email address.");

export const loginSchema = z.object({
  email,
  password: z.string().min(1, "Enter your password."),
});
export type LoginValues = z.infer<typeof loginSchema>;

const password = z
  .string()
  .min(8, "Use at least 8 characters.")
  .max(128, "Use at most 128 characters.");

// Sign-up asks for the account and the school. The rest of the profile is asked in setup.
export const signupSchema = z.object({
  fullName: z.string().trim().min(1, "Enter your name.").max(200, "Use at most 200 characters."),
  email,
  password,
  university: z.string().trim().max(150, "Use at most 150 characters."),
  acceptTerms: z
    .boolean()
    .refine(Boolean, "Please accept the Terms of Service and Privacy Policy."),
});
export type SignupValues = z.infer<typeof signupSchema>;
