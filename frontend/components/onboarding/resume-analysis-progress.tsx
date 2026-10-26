"use client";

import { useEffect, useState } from "react";
import { Check, Circle, Loader2, RotateCcw, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { ResumeAnalysis, ResumeAnalysisStep, ResumeStepEvent } from "@/types/api";

/** A step event plus when the browser received it (Date.now()), for the elapsed timer. */
export type TimedStepEvent = ResumeStepEvent & { at: number };

type ResumeAnalysisProgressProps = {
  file: File;
  /** Step events from streamResumeAnalysis, in the order they arrived. */
  events: TimedStepEvent[];
  /** Set once the analysis finished: every step is done and the summary shows. */
  result?: ResumeAnalysis;
  /** Set when the analysis failed: the running step turns red and shows this message. */
  error?: string;
  onCancel: () => void;
  onRetry: () => void;
  onChooseAnotherFile: () => void;
};

type RowStatus = "pending" | "running" | "done" | "failed";

type Row = {
  step: ResumeAnalysisStep;
  label: string;
  status: RowStatus;
  /** What the backend reported when the step finished. */
  detail?: string;
  startedAt?: number;
};

const LABELS: Record<ResumeAnalysisStep, string> = {
  upload: "Uploading and checking your file",
  extract: "Reading the text",
  ocr: "Scanning image pages (OCR)",
  classify: "Understanding your experience",
};

/** Clear progress lines for the agent-free steps; the Agent step fills the rest while it runs. */
const PROGRESS_BEFORE_AGENT = 30;
const PROGRESS_AGENT_CEILING = 95;
/** How fast the estimate approaches the ceiling: about two thirds of the way after this long. */
const AGENT_ESTIMATE_MS = 20_000;

/**
 * The card shown while a résumé is analyzed. Every row changes only on a real backend event; the
 * bar is an estimate while the Agent runs and reaches 100% only when the result arrives.
 */
export function ResumeAnalysisProgress({
  file,
  events,
  result,
  error,
  onCancel,
  onRetry,
  onChooseAnotherFile,
}: ResumeAnalysisProgressProps) {
  const rows = buildRows(events, Boolean(result), error);
  const running = rows.find((row) => row.status === "running");
  const now = useNow(Boolean(running));
  const progress = progressValue(events, Boolean(result), now);
  const summary = result ? summarize(result) : undefined;

  const announcement = error
    ? `Analysis failed: ${error}`
    : summary
      ? `Analysis complete. ${summary}`
      : running
        ? `${running.label}…`
        : "";

  return (
    <Card
      size="sm"
      className="mx-auto w-full max-w-120 animate-in fade-in-0 slide-in-from-bottom-2 duration-300 motion-reduce:animate-none"
    >
      <CardHeader>
        <CardTitle>
          {error
            ? "We couldn't finish reading your résumé"
            : summary
              ? "Your résumé is ready"
              : "Analyzing your résumé"}
        </CardTitle>
        <CardDescription className="flex min-w-0 items-center gap-1.5">
          <Upload aria-hidden className="size-3.5 shrink-0" />
          <span className="truncate">{file.name}</span>
        </CardDescription>
      </CardHeader>

      <CardContent className="grid gap-4">
        <Progress
          value={progress}
          aria-label="Analysis progress"
          indicatorClassName={cn(
            "duration-700 motion-reduce:transition-none",
            error && "bg-danger",
            summary && "bg-success",
          )}
        />

        <ol className="grid gap-3">
          {rows.map((row) => (
            <StepRow
              key={row.step}
              row={row}
              now={now}
              error={row.status === "failed" ? error : undefined}
            />
          ))}
        </ol>

        {summary && (
          <p className="flex items-center gap-2 rounded-lg bg-success-soft px-3 py-2 text-control font-medium text-foreground animate-in fade-in-0 motion-reduce:animate-none">
            <Check aria-hidden className="size-4 shrink-0 text-success" />
            {summary}
          </p>
        )}

        <p className="sr-only" aria-live="polite">
          {announcement}
        </p>

        {error ? (
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" onClick={onChooseAnotherFile}>
              Choose another file
            </Button>
            <Button type="button" onClick={onRetry}>
              <RotateCcw data-icon="inline-start" />
              Try again
            </Button>
          </div>
        ) : (
          !summary && (
            <div className="flex justify-end">
              <Button type="button" variant="ghost" onClick={onCancel}>
                Cancel
              </Button>
            </div>
          )
        )}
      </CardContent>
    </Card>
  );
}

function StepRow({ row, now, error }: { row: Row; now: number; error?: string }) {
  const showAgentNote = row.step === "classify" && row.status === "running";
  return (
    <li className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 animate-in fade-in-0 motion-reduce:animate-none">
      <StepIcon status={row.status} />
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3">
        <span
          className={cn(
            "text-control font-medium",
            row.status === "pending" && "text-muted-foreground",
            row.status === "failed" && "text-danger",
          )}
        >
          {row.label}
        </span>
        {row.status === "done" && row.detail && (
          <span className="text-xs text-muted-foreground">{row.detail}</span>
        )}
        {row.status === "running" && row.startedAt !== undefined && (
          <span className="text-xs tabular-nums text-muted-foreground">
            {formatElapsed(now - row.startedAt)}
          </span>
        )}
      </div>
      {showAgentNote && (
        <p className="col-start-2 text-xs text-muted-foreground">
          Our AI agent is reading your résumé for education, experience, projects and skills. This
          usually takes 10–60 seconds.
        </p>
      )}
      {error && <p className="col-start-2 text-xs text-danger">{error}</p>}
    </li>
  );
}

function StepIcon({ status }: { status: RowStatus }) {
  const base = "mt-0.5 size-4 shrink-0";
  if (status === "done") {
    return (
      <span className={cn(base, "grid place-items-center rounded-full bg-success text-white")}>
        <Check aria-hidden className="size-3" strokeWidth={3} />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className={cn(base, "grid place-items-center rounded-full bg-danger text-white")}>
        <X aria-hidden className="size-3" strokeWidth={3} />
      </span>
    );
  }
  if (status === "running") {
    return (
      <Loader2
        aria-hidden
        className={cn(base, "animate-spin text-primary motion-reduce:animate-none")}
      />
    );
  }
  return <Circle aria-hidden className={cn(base, "text-muted-foreground/40")} />;
}

/** The rows to show: OCR only when it ran; the first unfinished row fails when there's an error. */
function buildRows(events: TimedStepEvent[], finished: boolean, error?: string): Row[] {
  const started = new Map<ResumeAnalysisStep, TimedStepEvent>();
  const done = new Map<ResumeAnalysisStep, TimedStepEvent>();
  for (const event of events) {
    (event.status === "started" ? started : done).set(event.step, event);
  }

  const steps: ResumeAnalysisStep[] = ["upload", "extract"];
  if (started.has("ocr")) steps.push("ocr");
  steps.push("classify");

  let current = false;
  return steps.map((step, index) => {
    const finishedEvent = done.get(step);
    if (finishedEvent || finished) {
      const detail = finishedEvent && describe(finishedEvent);
      return { step, label: LABELS[step], status: "done", detail };
    }
    // Upload has no "started" event: it's running from the moment the request is sent.
    const isRunning = step === "upload" || started.has(step);
    const isCurrent = !current && (isRunning || index === 0);
    if (isCurrent) current = true;
    const status: RowStatus = isCurrent && error ? "failed" : isRunning ? "running" : "pending";
    return { step, label: LABELS[step], status, startedAt: started.get(step)?.at };
  });
}

function describe(event: TimedStepEvent): string | undefined {
  const detail = event.detail;
  switch (event.step) {
    case "upload":
      return [detail.file_type?.toUpperCase(), detail.bytes !== undefined && formatBytes(detail.bytes)]
        .filter(Boolean)
        .join(" · ");
    case "extract":
      if (detail.characters === undefined) return undefined;
      return `${detail.characters.toLocaleString()} characters`;
    case "ocr":
      return detail.pages && plural(detail.pages.length, "page");
    case "classify":
      return detail.validated ? "Validated" : undefined;
  }
}

function progressValue(events: TimedStepEvent[], finished: boolean, now: number): number {
  if (finished) return 100;
  const last = events.at(-1);
  if (!last) return 3;
  if (last.step === "classify" && last.status === "started") {
    const elapsed = Math.max(0, now - last.at);
    const share = 1 - Math.exp(-elapsed / AGENT_ESTIMATE_MS);
    return PROGRESS_BEFORE_AGENT + (PROGRESS_AGENT_CEILING - PROGRESS_BEFORE_AGENT) * share;
  }
  const reached: Record<string, number> = {
    "upload done": 10,
    "extract started": 15,
    "ocr started": 18,
    "ocr done": 27,
    "extract done": PROGRESS_BEFORE_AGENT,
    "classify done": PROGRESS_AGENT_CEILING,
  };
  return reached[`${last.step} ${last.status}`] ?? 3;
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

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
