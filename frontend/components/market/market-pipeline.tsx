import { Check, Circle, LoaderCircle, TriangleAlert } from "lucide-react";

import type { SkillGapRun } from "@/types/api";

type PipelineState = "complete" | "running" | "waiting" | "failed";
type MarketPipelineProps = {
  confirmed: boolean;
  marketLoaded: boolean;
  marketLoading: boolean;
  marketError?: string;
  run: SkillGapRun | null;
  submitting: boolean;
};

/** The current stages describe actual data sources, not four assumed Agent calls. */
export function getMarketPipelineSteps({ confirmed, marketLoaded, marketLoading, marketError, run, submitting }: MarketPipelineProps) {
  let gapState: PipelineState = "waiting";
  let gapDetail = confirmed ? "Ready to analyze your reviewed résumé" : "Waiting for résumé confirmation";
  if (submitting) { gapState = "running"; gapDetail = "Starting your analysis"; }
  else if (run?.status === "queued") { gapState = "running"; gapDetail = "Queued for analysis"; }
  else if (run?.status === "running") {
    gapState = "running";
    gapDetail = run.phase === "checking" || run.phase === "scoring"
      ? "Checking evidence and calculating gaps" : "Reading résumé evidence";
  } else if (run?.status === "completed") { gapState = "complete"; gapDetail = "Evidence scored and skill gaps calculated"; }
  else if (run?.status === "failed") { gapState = "failed"; gapDetail = "Analysis could not finish · retry in Skill Gaps"; }
  return [
    { name: "Student profile", state: confirmed ? "complete" as const : "waiting" as const,
      detail: confirmed ? "Reviewed résumé confirmed" : "Upload and review your résumé" },
    { name: "Market demand", state: marketLoaded ? "complete" as const : marketLoading ? "running" as const : marketError ? "failed" as const : "waiting" as const,
      detail: marketLoaded ? "Saved job-demand snapshot loaded" : marketLoading ? "Loading job-demand snapshot" : marketError ? "Snapshot unavailable · try loading again" : "Choose a target role" },
    { name: "Skill gap analysis", state: gapState, detail: gapDetail },
    { name: "Action plan", state: "waiting" as const, detail: "Not available yet" },
  ];
}

const STYLES: Record<PipelineState, string> = {
  complete: "bg-success-soft text-success",
  running: "bg-accent text-primary",
  waiting: "border bg-card text-muted-foreground",
  failed: "bg-warning-soft text-warning",
};

export function MarketPipeline(props: MarketPipelineProps) {
  const steps = getMarketPipelineSteps(props);
  return <ol className="grid gap-3.5" aria-label="Current analysis stages">
    {steps.map((step, index) => {
      const Icon = step.state === "complete" ? Check : step.state === "running" ? LoaderCircle
        : step.state === "failed" ? TriangleAlert : Circle;
      return <li key={step.name} className="relative flex items-start gap-3">
        {index < steps.length - 1 && <span aria-hidden="true" className="absolute top-6.5 -bottom-3 left-[0.6875rem] w-px bg-border" />}
        <span className={`grid size-5.5 shrink-0 place-items-center rounded-full ${STYLES[step.state]}`}>
          <Icon aria-hidden="true" className={`size-3 ${step.state === "running" ? "motion-safe:animate-spin" : ""}`} />
        </span>
        <div className="min-w-0"><p className="text-control font-semibold">{step.name}</p><p className="text-xs text-muted-foreground">{step.detail}</p></div>
      </li>;
    })}
  </ol>;
}
