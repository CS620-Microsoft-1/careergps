"use client";

import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";

import { StatusCard, StepList } from "@/components/career/route-parts";
import { Button } from "@/components/ui/button";
import type { ResumeAnalysis, ResumeAnalysisStep, ResumeStepEvent } from "@/types/api";

/** A step event plus when the browser received it (Date.now()), for the elapsed timer. */
export type TimedStepEvent = ResumeStepEvent & { at: number };

type ResumeAnalysisProgressProps = {
  file: File;
  /** When the analysis was sent (Date.now()), for the elapsed time. */
  started: number;
  /** Step events from streamResumeAnalysis, in the order they arrived. */
  events: TimedStepEvent[];
  /** Set once the analysis finished: every step is done and the summary shows. */
  result?: ResumeAnalysis;
  /** Set when the analysis failed: shown with Try again in place of the steps. */
  error?: string;
  onCancel: () => void;
  onRetry: () => void;
  onChooseAnotherFile: () => void;
};

const LABELS: Record<ResumeAnalysisStep, string> = {
  upload: "Upload file",
  extract: "Read the text",
  ocr: "Scan image pages",
  classify: "Understand your experience",
};

/**
 * The card shown while a résumé is read, in the same style as the route's analysis card. Every step
 * changes only on a real backend event.
 */
export function ResumeAnalysisProgress({ file, started, events, result, error, onCancel, onRetry, onChooseAnotherFile }: ResumeAnalysisProgressProps) {
  const steps = buildSteps(events, Boolean(result));
  const busy = !result && !error;
  const now = useNow(busy);
  const seconds = Math.max(0, Math.floor((now - started) / 1000));
  const agentRunning = steps.some((step) => step.step === "classify" && step.active);

  return (
    <StatusCard busy={busy}
      title={error ? "We couldn’t finish reading your résumé" : result ? "Your résumé is ready" : "Analyzing your résumé"}
      detail={error ?? (result ? summarize(result) : <>
        {file.name} · {seconds} seconds so far.
        {agentRunning && " Our AI agent is reading it for education, experience, projects and skills. This usually takes 10–60 seconds."}
      </>)}
      steps={!error && <StepList label="Résumé steps" steps={steps} />}
      action={error ? <>
        <Button size="lg" variant="outline" onClick={onChooseAnotherFile}>Choose another file</Button>
        <Button size="lg" onClick={onRetry}><RotateCcw data-icon="inline-start" />Try again</Button>
      </> : busy && <Button size="lg" variant="ghost" onClick={onCancel}>Cancel</Button>} />
  );
}

/** The steps to show: OCR only when it ran. */
function buildSteps(events: TimedStepEvent[], finished: boolean) {
  const started = new Set<ResumeAnalysisStep>();
  const done = new Set<ResumeAnalysisStep>();
  for (const event of events) (event.status === "started" ? started : done).add(event.step);

  const steps: ResumeAnalysisStep[] = ["upload", "extract"];
  if (started.has("ocr")) steps.push("ocr");
  steps.push("classify");
  return steps.map((step) => {
    const isDone = finished || done.has(step);
    // Upload has no "started" event: it's running from the moment the request is sent.
    return { step, label: LABELS[step], done: isDone, active: !isDone && (step === "upload" || started.has(step)) };
  });
}

/** "Found 3 experiences · 14 skills · 2 projects" from the classified résumé. */
function summarize({ classification }: ResumeAnalysis): string {
  const experiences = classification.work_experience.length + classification.research_experience.length;
  return `Found ${[
    plural(experiences, "experience"),
    plural(classification.technical_skills.length, "skill"),
    plural(classification.projects.length, "project"),
  ].join(" · ")}`;
}

/** The current time, refreshed every second while `active`. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}
