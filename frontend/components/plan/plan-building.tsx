"use client";

import { useEffect, useState } from "react";
import NumberFlow from "@number-flow/react";
import { Check, LoaderCircle } from "lucide-react";

import { RESOURCE_TYPES, numberTiming } from "@/components/career/route-parts";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ActionPlanBuildStage, ResourceType } from "@/types/api";

/** How long each shortlisted title stays in the "Weighing" ticker. */
export const TICKER_MS = 1500;
const COUNT_ORDER: ResourceType[] = ["project", "certification", "school_course", "online_course", "student_org"];

type StepState = "done" | "active" | "waiting";

/**
 * The live view while a plan is built: the real stages the backend reports (gaps read, shortlist made,
 * the Agent choosing, the plan checked), with the real gaps, counts and shortlisted titles. No progress
 * percentage: the Agent's thinking time isn't knowable in advance, so only the elapsed time is shown.
 */
export function PlanBuilding({ stages, onCancel }: { stages: ActionPlanBuildStage[]; onCancel: () => void }) {
  const gaps = find(stages, "gaps");
  const candidates = find(stages, "candidates");
  const seen = new Set(stages.map((stage) => stage.stage));
  const fellBack = seen.has("rules");
  const total = candidates ? Object.values(candidates.counts).reduce((sum, count) => sum + (count ?? 0), 0) : 0;

  const steps: { key: string; state: StepState; label: string; detail?: React.ReactNode }[] = [
    { key: "gaps", state: gaps ? "done" : "active",
      label: gaps ? `Read your ${plural(gaps.gaps.length, "gap")}` : "Reading your gaps",
      detail: gaps && <ul aria-label="Your gaps" className="flex flex-wrap gap-1.5">
        {gaps.gaps.map((gap, index) => (
          <li key={gap.skill_id} className="entrance-pop rounded-full bg-card px-2.5 py-1 text-xs font-bold motion-safe:[animation-delay:var(--delay)]"
            style={delay(index * 60)}>{gap.skill_name}</li>
        ))}
      </ul> },
    { key: "candidates", state: candidates ? "done" : gaps ? "active" : "waiting",
      label: candidates ? `Shortlisted ${plural(total, "resource")} that close them` : "Shortlisting resources that close them",
      detail: candidates && <p className="flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted-foreground">
        {COUNT_ORDER.filter((type) => candidates.counts[type]).map((type) => (
          <span key={type}><b className="font-mono font-medium text-foreground"><Count value={candidates.counts[type]!} /></b>{" "}
            {(candidates.counts[type] === 1 ? RESOURCE_TYPES[type].label : RESOURCE_TYPES[type].plural).toLowerCase()}</span>
        ))}
      </p> },
    { key: "mentor",
      state: seen.has("cached") || seen.has("checking") || (fellBack && !seen.has("agent")) ? "done"
        : seen.has("agent") || fellBack ? "active" : "waiting",
      label: seen.has("cached") ? "Found the plan your mentor already built"
        : fellBack ? (seen.has("agent") ? "Mentor unavailable, building from your gap ranking instead" : "Building from your gap ranking")
        : seen.has("checking") ? "Your mentor chose and ordered the steps"
        : "Your mentor is choosing and ordering the steps",
      detail: seen.has("agent") && !seen.has("checking") && !fellBack && candidates && <Ticker samples={candidates.samples} /> },
    { key: "checking", state: seen.has("checking") || seen.has("cached") || fellBack ? "active" : "waiting",
      label: "Checking the plan against your gaps" },
  ];
  // What to announce: the stage in progress, else the latest one finished.
  const current = steps.find((step) => step.state === "active")
    ?? steps.findLast((step) => step.state === "done") ?? steps[0];

  return (
    <div className="mt-6 grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 font-bold">
          <LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />Building your plan
        </p>
        <Elapsed />
      </div>
      {/* Screen readers hear each stage once; the ticker stays silent. */}
      <p role="status" className="sr-only">{current.label}</p>
      <ol aria-label="Plan building steps" className="grid gap-3 rounded-xl bg-sunken p-4 sm:p-5">
        {steps.map((step, index) => (
          <li key={step.key} aria-current={step.state === "active" ? "step" : undefined}
            className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-3 gap-y-2">
            <span aria-hidden className={cn("grid size-6 place-items-center rounded-full text-xs font-bold",
              step.state === "done" ? "bg-foreground text-background" : step.state === "active" ? "bg-accent" : "bg-card")}>
              {step.state === "done" ? <Check className="entrance-pop size-3.5" />
                : step.state === "active" ? <span className="size-2 rounded-full bg-foreground motion-safe:animate-pulse" />
                : index + 1}
            </span>
            <p className={cn("min-w-0 self-center text-sm", step.state === "waiting" ? "text-muted-foreground" : "font-bold")}>
              {step.label}{step.state === "active" && step.key !== "checking" ? "…" : ""}
              <span className="sr-only">{step.state === "done" ? ": done" : step.state === "active" ? ": in progress" : ": waiting"}</span>
            </p>
            {step.detail && <div className="col-start-2 min-w-0">{step.detail}</div>}
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">A first plan can take up to a minute. A repeat comes back at once.</p>
        <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}

/** Shortlisted titles, one at a time, while the Agent decides. Static under reduced motion. */
function Ticker({ samples }: { samples: { title: string; type: ResourceType }[] }) {
  const [index, setIndex] = useState(0);
  const [still, setStill] = useState(false);
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (reduce || samples.length < 2) {
      // Synced from a browser setting after mount, not during render.
      void Promise.resolve().then(() => setStill(reduce));
      return;
    }
    const timer = setInterval(() => setIndex((current) => (current + 1) % samples.length), TICKER_MS);
    return () => clearInterval(timer);
  }, [samples.length]);
  if (!samples.length) return null;
  if (still) {
    return <p aria-hidden className="text-sm text-muted-foreground">
      Weighing {samples.slice(0, 3).map((sample) => sample.title).join(", ")} and more
    </p>;
  }
  const sample = samples[index];
  return (
    <p aria-hidden className="flex min-w-0 items-baseline gap-2 text-sm">
      <span className="shrink-0 text-muted-foreground">Weighing</span>
      <span key={index} className="entrance-rise min-w-0 truncate">
        <b>{sample.title}</b><span className="text-muted-foreground"> · {RESOURCE_TYPES[sample.type].label}</span>
      </span>
    </p>
  );
}

/** Counts up from 0 when it appears. */
function Count({ value }: { value: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setShown(value));
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <NumberFlow value={shown} {...numberTiming(500)} />;
}

/** Seconds since the build started, as m:ss. */
function Elapsed() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);
  // Hidden from screen readers: a ticking clock would be read out every second.
  return <p aria-hidden className="font-mono text-sm text-muted-foreground">
    {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
  </p>;
}

function find<S extends ActionPlanBuildStage["stage"]>(stages: ActionPlanBuildStage[], stage: S) {
  return stages.find((item): item is Extract<ActionPlanBuildStage, { stage: S }> => item.stage === stage);
}

/** A stagger delay, applied only when motion is allowed (see the motion-safe:[animation-delay] classes). */
const delay = (ms: number) => ({ "--delay": `${ms}ms` }) as React.CSSProperties;

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;
