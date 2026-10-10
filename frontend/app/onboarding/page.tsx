import type { Metadata } from "next";

import { AuthHeading, AuthShell } from "@/components/auth/auth-shell";
import { OnboardingForm } from "@/components/auth/onboarding-form";
import { getGraduationYears } from "@/lib/graduation-years";

export const metadata: Metadata = { title: "Your career goal" };

export default async function OnboardingPage() {
  return (
    <AuthShell
      title="Where do you want your career to go?"
      description="Tell us your goal. We'll compare your experience with real job-market data and map the clearest path forward."
    >
      <AuthHeading title="Your career goal" subtitle="You can change this anytime." />
      <OnboardingForm graduationYears={await getGraduationYears()} />
    </AuthShell>
  );
}
