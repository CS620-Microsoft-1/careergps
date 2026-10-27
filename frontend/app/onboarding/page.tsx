import type { Metadata } from "next";
import { Suspense } from "react";

import { SetupFlow } from "@/components/setup/setup-flow";
import { getGraduationYears } from "@/lib/graduation-years";

export const metadata: Metadata = { title: "Set up your route" };

export default async function OnboardingPage() {
  const graduationYears = await getGraduationYears();
  // ?step= is read in the browser (useSearchParams), so the flow renders below a Suspense boundary.
  return (
    <Suspense fallback={<p className="text-muted-foreground">Loading…</p>}>
      <SetupFlow graduationYears={graduationYears} />
    </Suspense>
  );
}
