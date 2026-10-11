import type { Metadata } from "next";

import { Logo } from "@/components/common/logo";
import { ResumeReview } from "@/components/onboarding/resume-review";

export const metadata: Metadata = { title: "Check your résumé" };

export default function ResumeReviewPage() {
  return (
    <div className="min-h-dvh bg-background">
      <header className="border-b border-border px-6 py-4 sm:px-10">
        <Logo />
      </header>
      <main className="mx-auto w-full max-w-2xl px-6 py-10 sm:px-10">
        <ResumeReview />
      </main>
    </div>
  );
}
