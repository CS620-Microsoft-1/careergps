import type { Metadata } from "next";

import { AuthHeading, AuthShell } from "@/components/auth/auth-shell";
import { OnboardingForm } from "@/components/auth/onboarding-form";

export const metadata: Metadata = { title: "Upload your résumé" };

export default function OnboardingPage() {
  return (
    <AuthShell
      title="Where do you want your career to go?"
      description="Share your résumé. We'll compare your experience with real job-market data and map the clearest path forward."
    >
      <AuthHeading title="Upload your résumé" subtitle="You'll check what we found before anything is saved." />
      <OnboardingForm />
    </AuthShell>
  );
}
