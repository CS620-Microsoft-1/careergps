import type { Metadata } from "next";

import { SetupFlow } from "@/components/setup/setup-flow";
import { getGraduationYears } from "@/lib/graduation-years";

export const metadata: Metadata = { title: "Set up your route" };

/** ?step=role: only choose another target role for the saved résumé (Add a destination). */
export default async function OnboardingPage({ searchParams }: PageProps<"/onboarding">) {
  const { step } = await searchParams;
  return <SetupFlow graduationYears={await getGraduationYears()} addRole={step === "role"} />;
}
