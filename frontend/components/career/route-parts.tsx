"use client";

import Link from "next/link";
import {
  Award,
  Bookmark,
  BookmarkCheck,
  Check,
  GraduationCap,
  Info,
  LoaderCircle,
  Monitor,
  RotateCcw,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import { usePlan } from "@/components/plan/plan-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Button } from "@/components/ui/button";
import { EVIDENCE_LABELS, STRONG_STRENGTH, demandShare, evidenceLevel, percent } from "@/lib/career";
import { SKILL_LABELS } from "@/lib/skill-gap-labels";
import { cn } from "@/lib/utils";
import type { CoreSkillResult, JobFamily, ResourceType } from "@/types/api";

/** Sentence-case role names, as the design writes them ("Data analyst"). */
export const ROLE_NAMES: Record<JobFamily, string> = {
  software_engineer: "Software engineer",
  data_analyst: "Data analyst",
  ai_engineer: "AI engineer",
};

export const skillLabel = (id: string) => SKILL_LABELS[id] ?? id.replaceAll("_", " ");

export const RESOURCE_TYPES: Record<ResourceType, { label: string; plural: string; blurb: string; icon: LucideIcon }> = {
  student_org: { label: "Student org", plural: "Student organizations", blurb: "On your campus", icon: Users },
  certification: { label: "Certification", plural: "Certifications", blurb: "Credentials employers recognize", icon: Award },
  online_course: { label: "Online course", plural: "Online courses and programs", blurb: "Learn on your own schedule", icon: Monitor },
  school_course: { label: "Course", plural: "Courses at your school", blurb: "Plan ahead for registration", icon: GraduationCap },
  project: { label: "Project", plural: "Projects", blurb: "Proof you can show in interviews", icon: Wrench },
};
export const RESOURCE_TYPE_ORDER: ResourceType[] = ["student_org", "certification", "online_course", "school_course", "project"];

export function ResourceIcon({ type, className }: { type: ResourceType; className?: string }) {
  const Icon = RESOURCE_TYPES[type].icon;
  return (
    <span aria-hidden className={cn("grid size-9 shrink-0 place-items-center rounded-full bg-card", className)}>
      <Icon className="size-4.5" />
    </span>
  );
}

/** Progress ring with the match percent in the middle. value is 0–1, or null while unknown. */
export function MatchRing({ value, size = 160, stroke = 14, label = "match", className }: {
  value: number | null; size?: number; stroke?: number; label?: string | null; className?: string;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const shown = value === null ? 0 : Math.min(1, Math.max(0, value));
  return (
    <div className={cn("relative grid shrink-0 place-items-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--sunken)" strokeWidth={stroke} />
        {value !== null && (
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--foreground)" strokeWidth={stroke}
            strokeLinecap="round" strokeDasharray={`${shown * circumference} ${circumference}`} />
        )}
      </svg>
      <div className="absolute text-center">
        <p className="font-extrabold tracking-[-0.02em]" style={{ fontSize: Math.max(14, size * 0.22), lineHeight: 1.1 }}>
          {value === null ? "—" : percent(value)}
        </p>
        {label && size >= 96 && <p className="text-sm text-muted-foreground">{label}</p>}
      </div>
    </div>
  );
}

/**
 * You-vs-market bar on the evidence-strength scale. Black = your résumé evidence, hatched = the gap
 * up to the tick, which marks strong evidence (where a skill stops counting as a gap).
 */
export function GapBar({ skill, className }: { skill: CoreSkillResult; className?: string }) {
  const strength = Math.min(1, Math.max(0, skill.resume_evidence_strength ?? 0));
  const target = STRONG_STRENGTH * 100;
  return (
    <div className={cn("relative h-2.5 rounded-full bg-sunken", className)} role="img"
      aria-label={`${skillLabel(skill.skill_id)}: ${EVIDENCE_LABELS[evidenceLevel(strength)].toLowerCase()}, asked for in ${percent(demandShare(skill))} of postings`}>
      <span className="absolute inset-y-0 left-0 rounded-full bg-foreground" style={{ width: `${strength * 100}%` }} />
      {strength * 100 < target && (
        <span className="bg-hatch absolute inset-y-0" style={{ left: `${strength * 100}%`, width: `${target - strength * 100}%` }} />
      )}
      <span className="absolute -top-1 -bottom-1 w-0.5 -translate-x-1/2 rounded-full bg-foreground" style={{ left: `${target}%` }} />
    </div>
  );
}

export function GapMeta({ skill }: { skill: CoreSkillResult }) {
  return (
    <p className="text-sm text-muted-foreground">
      You: {EVIDENCE_LABELS[evidenceLevel(skill.resume_evidence_strength ?? 0)]} · In {percent(demandShare(skill))} of postings
    </p>
  );
}

export function GapLegend() {
  return (
    <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1.5"><span aria-hidden className="h-1.5 w-3 rounded-full bg-foreground" />You</span>
      <span className="inline-flex items-center gap-1.5"><span aria-hidden className="bg-hatch h-1.5 w-3 rounded-full" />Gap</span>
      <span className="inline-flex items-center gap-1.5"><span aria-hidden className="h-3 w-0.5 bg-foreground" />Strong evidence</span>
    </p>
  );
}

/** Save to plan / Saved to plan / Done, for one resource. */
export function SaveButton({ resourceId, tone = "card", className }: {
  resourceId: string; tone?: "card" | "tile"; className?: string;
}) {
  const { saved, pending, toggleSaved } = usePlan();
  const item = saved.get(resourceId);
  const busy = pending.has(resourceId);
  if (item?.status === "done") {
    return <span className={cn("inline-flex h-9 items-center gap-1.5 text-sm font-bold text-success", className)}>
      <Check aria-hidden className="size-4" />Done</span>;
  }
  return (
    <Button type="button" size="sm" variant={item ? "accent" : tone === "tile" ? "raised" : "secondary"}
      aria-pressed={Boolean(item)} disabled={busy} onClick={() => void toggleSaved(resourceId)} className={className}>
      {busy ? <LoaderCircle data-icon="inline-start" className="motion-safe:animate-spin" />
        : item ? <BookmarkCheck data-icon="inline-start" /> : <Bookmark data-icon="inline-start" />}
      {item ? "Saved to plan" : "Save to plan"}
    </Button>
  );
}

type PageHeaderProps = {
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Right side: a summary card or buttons; drops below the title when narrow. */
  aside?: React.ReactNode;
};

export function RoutePageHeader({ title, description, aside }: PageHeaderProps) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
      <div className="min-w-0 flex-1 basis-96">
        <h1 className="text-page-title">{title}</h1>
        {description && <p className="mt-2 max-w-3xl text-base/7 text-muted-foreground">{description}</p>}
      </div>
      {aside}
    </div>
  );
}

export function SourceNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-sm text-muted-foreground">
      <Info aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

/**
 * Shown in place of results until the analysis for the selected role is ready: loading, running,
 * failed, or never run. Returns null once there is a completed report.
 */
export function AnalysisGate({ children }: { children?: React.ReactNode }) {
  const { loaded, snapshot, family, run, submitting, restoring, error, elapsed, analyze } = useSkillGapAnalysis();
  if (run?.status === "completed" && run.report) return null;
  const busy = submitting || run?.status === "queued" || run?.status === "running";
  const calculating = run?.phase === "checking" || run?.phase === "scoring";
  const failed = run?.status === "failed";

  let title: string;
  let detail: string;
  let action: React.ReactNode = null;
  if (!loaded || restoring) {
    title = "Loading your route…";
    detail = "Your confirmed résumé and saved analysis will appear in a moment.";
  } else if (!snapshot) {
    title = "Upload your résumé to start";
    detail = error ?? "We compare your confirmed résumé with real job postings, then show your gaps and a plan.";
    action = <Button asChild size="lg"><Link href="/onboarding">Upload résumé</Link></Button>;
  } else if (busy) {
    title = calculating ? "Calculating your gaps" : run?.phase === "queued" ? "Your analysis is in the queue"
      : "Reading the evidence in your résumé";
    detail = `${Math.max(0, Math.floor(elapsed))} seconds so far. This can take a minute or two; you can leave this page.`;
  } else if (failed) {
    title = "The analysis couldn’t finish";
    detail = run?.error ?? "Your confirmed résumé is safe. Try again in a moment.";
    action = <Button size="lg" onClick={() => void analyze(true)}><RotateCcw data-icon="inline-start" />Try again</Button>;
  } else {
    title = `No route to ${ROLE_NAMES[family]} yet`;
    detail = error ?? `Compare your confirmed résumé with ${ROLE_NAMES[family].toLowerCase()} postings to see your match and gaps.`;
    action = <Button size="lg" onClick={() => void analyze(false)}>Calculate my route</Button>;
  }
  return (
    <div className="grid justify-items-center gap-3 rounded-2xl border border-border bg-card px-6 py-14 text-center" aria-busy={busy}>
      {(busy || !loaded || restoring) && <LoaderCircle aria-hidden className="size-7 motion-safe:animate-spin" />}
      <div role="status" aria-live="polite" className="grid gap-1.5">
        <h2 className="text-section">{title}</h2>
        <p className="mx-auto max-w-lg text-muted-foreground">{detail}</p>
      </div>
      {busy && <AnalysisSteps calculating={calculating} />}
      {action && <div className="mt-2">{action}</div>}
      {children}
    </div>
  );
}

function AnalysisSteps({ calculating }: { calculating: boolean }) {
  const steps = [
    { label: "Résumé confirmed", done: true, active: false },
    { label: "Read skill evidence", done: calculating, active: !calculating },
    { label: "Calculate gaps", done: false, active: calculating },
  ];
  return (
    <ol aria-label="Analysis steps" className="mt-2 flex flex-wrap justify-center gap-x-5 gap-y-2 text-sm">
      {steps.map((step, index) => (
        <li key={step.label} aria-current={step.active ? "step" : undefined}
          className={cn("flex items-center gap-2", !step.done && !step.active && "text-muted-foreground")}>
          <span className={cn("grid size-6 place-items-center rounded-full text-xs font-bold",
            step.done ? "bg-foreground text-background" : step.active ? "bg-accent" : "bg-sunken")}>
            {step.done ? <Check aria-hidden className="size-3.5" /> : index + 1}
          </span>
          {step.label}
          <span className="sr-only">{step.done ? ": done" : step.active ? ": in progress" : ": waiting"}</span>
        </li>
      ))}
    </ol>
  );
}
