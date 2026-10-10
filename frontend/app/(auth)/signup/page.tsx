import type { Metadata } from "next";

import { AuthHeading } from "@/components/auth/auth-shell";
import { SignupForm } from "@/components/auth/signup-form";
import { getGraduationYears } from "@/lib/graduation-years";

export const metadata: Metadata = { title: "Create account" };

export default async function SignupPage() {
  return (
    <>
      <AuthHeading title="Create your account" subtitle="It takes less than a minute." />
      <SignupForm graduationYears={await getGraduationYears()} />
    </>
  );
}
