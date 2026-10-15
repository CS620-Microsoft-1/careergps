import type { Metadata } from "next";

import { AuthHeading } from "@/components/auth/auth-shell";
import { SignupForm } from "@/components/auth/signup-form";

export const metadata: Metadata = { title: "Create account" };

export default function SignupPage() {
  return (
    <>
      <AuthHeading title="Create your account" subtitle="It takes less than a minute." />
      <SignupForm />
    </>
  );
}
