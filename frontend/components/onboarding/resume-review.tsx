"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2 } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { ResumeReviewForm } from "@/components/onboarding/resume-review-form";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/client";
import { getMe } from "@/lib/api/me";
import { getResume, retryResume } from "@/lib/api/resumes";
import type { Resume, ResumeErrorCode } from "@/types/api";

const POLL_INTERVAL_MS = 2000;
const POLL_LIMIT_MS = 2 * 60 * 1000;

const FAILURE_MESSAGES: Record<ResumeErrorCode, string> = {
  no_text: "We couldn't read text from this file. Try exporting it again as a PDF.",
  llm_invalid_output: "Something went wrong reading your résumé. Try again.",
  llm_unavailable: "Something went wrong reading your résumé. Try again.",
  internal: "Something went wrong reading your résumé. Try again.",
};

type Phase =
  | { kind: "loading" }
  | { kind: "parsing" }
  | { kind: "parsed"; resume: Resume }
  | { kind: "failed"; resume: Resume }
  | { kind: "timeout" }
  | { kind: "error"; message: string };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Waits for the résumé to be parsed, then shows "Here is what we identified" (SPEC-001 §9). */
export function ResumeReview() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  // Bumped to start polling again (after a retry).
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const me = await getMe();
        const summary = me.latest_resume;
        if (!summary) return router.replace("/onboarding");

        const deadline = Date.now() + POLL_LIMIT_MS;
        while (!cancelled && Date.now() < deadline) {
          const resume = await getResume(summary.id);
          if (cancelled) return;
          switch (resume.status) {
            case "confirmed":
              return router.replace("/dashboard");
            case "parsed":
              return setPhase({ kind: "parsed", resume });
            case "failed":
              return setPhase({ kind: "failed", resume });
            default:
              setPhase({ kind: "parsing" });
              await sleep(POLL_INTERVAL_MS);
          }
        }
        if (!cancelled) setPhase({ kind: "timeout" });
      } catch (error) {
        if (!cancelled) setPhase({ kind: "error", message: errorMessage(error) });
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [attempt, router]);

  const retry = useCallback(async (resumeId: string) => {
    setPhase({ kind: "parsing" });
    try {
      await retryResume(resumeId);
      setAttempt((n) => n + 1);
    } catch (error) {
      setPhase({ kind: "error", message: errorMessage(error) });
    }
  }, []);

  switch (phase.kind) {
    case "loading":
    case "parsing":
      return (
        <div role="status" className="grid justify-items-center gap-2 py-16 text-center">
          <Loader2 aria-hidden className="size-6 animate-spin text-primary" />
          <p className="font-semibold">Reading your résumé…</p>
          <p className="text-control text-muted-foreground">This usually takes under a minute.</p>
        </div>
      );
    case "parsed":
      return (
        <ResumeReviewForm
          resume={phase.resume}
          onConfirmed={() => router.push("/dashboard")}
        />
      );
    case "failed":
      return (
        <EmptyState
          icon={AlertTriangle}
          title="We couldn't read your résumé"
          description={FAILURE_MESSAGES[phase.resume.error_code ?? "internal"]}
          action={
            <div className="flex flex-wrap justify-center gap-2">
              {phase.resume.error_code !== "no_text" && (
                <Button onClick={() => retry(phase.resume.id)}>Try again</Button>
              )}
              <Button variant="outline" asChild>
                <Link href="/onboarding">Upload a different file</Link>
              </Button>
            </div>
          }
        />
      );
    case "timeout":
      return (
        <EmptyState
          icon={AlertTriangle}
          title="This is taking longer than usual"
          description="Your résumé is still being read. Check again in a minute."
          action={<Button onClick={() => setAttempt((n) => n + 1)}>Check again</Button>}
        />
      );
    case "error":
      return (
        <EmptyState
          icon={AlertTriangle}
          title="Something went wrong"
          description={phase.message}
          action={<Button onClick={() => setAttempt((n) => n + 1)}>Try again</Button>}
        />
      );
  }
}
