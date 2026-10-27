"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, ChevronDown, ChevronRight, Download, RotateCcw } from "lucide-react";

import {
  AnalysisGate,
  GapBar,
  GapMeta,
  MatchRing,
  RESOURCE_TYPES,
  ROLE_NAMES,
  ResourceIcon,
  RoutePageHeader,
  SaveButton,
  SourceNote,
  skillLabel,
} from "@/components/career/route-parts";
import { SkillEvidence } from "@/components/gaps/skill-evidence";
import { usePlan } from "@/components/plan/plan-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DEMAND_LABELS,
  demandLevel,
  demandShare,
  needsReview,
  percent,
  rankGaps,
  rankStrengths,
  resourcesForSkill,
} from "@/lib/career";
import { cn } from "@/lib/utils";
import type { CoreSkillGapReport, CoreSkillResult, SkillGapRun } from "@/types/api";

/** Gaps open with their ways to close them; the rest open on request. */
const EXPANDED = 3;

export function GapsView() {
  const { family, run, snapshot } = useSkillGapAnalysis();
  const role = ROLE_NAMES[family];
  // The session starts on a default role until the profile loads; don't name it before then.
  const eyebrow = snapshot ? `Gaps · ${role}` : "Gaps";
  if (run?.status !== "completed" || !run.report || !snapshot) {
    return <>
      <RoutePageHeader eyebrow={eyebrow} title="Your gaps" />
      <AnalysisGate />
    </>;
  }
  const report = run.report;
  const gaps = rankGaps(report);
  const strengths = rankStrengths(report);
  const review = needsReview(report);
  const sample = report.skills[0]?.demand.N;

  return <>
    <RoutePageHeader eyebrow={`Gaps · ${role}`}
      title={gaps.length === 1 ? "1 gap to close" : `${gaps.length} gaps to close`}
      description="Ranked by how often employers ask for them and how little your résumé shows. Close one and your match goes up."
      aside={<div className="flex items-center gap-4 rounded-2xl border border-border bg-card px-5 py-4 shadow-card">
        <MatchRing value={run.match?.score ?? null} size={72} stroke={8} label={null} />
        <div>
          <p className="font-bold">{run.match ? `${percent(run.match.score)} match` : "Match not available"}</p>
          <p className="text-sm text-muted-foreground">{strengths.length} strengths · {review.length} to review</p>
        </div>
      </div>} />
    {sample && <div className="-mt-4 mb-8"><SourceNote>Based on {sample.toLocaleString()} {role.toLowerCase()} job postings in the current market snapshot.</SourceNote></div>}

    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <div className="grid gap-5">
        {gaps.length === 0 && <div className="rounded-2xl bg-success-soft p-6">
          <h2 className="text-title">No gaps left for {role.toLowerCase()}</h2>
          <p className="mt-1">Every skill postings ask for shows strong evidence in your résumé.</p>
        </div>}
        {gaps.map((gap, index) => <GapCard key={gap.skill_id} gap={gap} rank={index + 1} report={report}
          variant={index === 0 ? "lead" : index < EXPANDED ? "open" : "closed"} />)}
      </div>

      <aside className="grid gap-5">
        <section aria-labelledby="strengths" className="rounded-2xl border border-border bg-card p-6 shadow-card">
          <h2 id="strengths" className="text-title">Already strengths</h2>
          {strengths.length ? <ul className="mt-3 flex flex-wrap gap-2">
            {strengths.map((skill) => <li key={skill.skill_id}><Badge variant="success">{skillLabel(skill.skill_id)}</Badge></li>)}
          </ul> : <p className="mt-2 text-sm text-muted-foreground">None yet. Skills move here once your résumé shows strong evidence.</p>}
          <p className="mt-4 text-sm text-muted-foreground">From {snapshot.filename}. <Link href="/profile" className="font-bold text-foreground underline">See it in Profile</Link></p>
        </section>
        {review.length > 0 && <section aria-labelledby="review" className="rounded-2xl bg-warning-soft p-6">
          <h2 id="review" className="text-title">Needs your review</h2>
          <p className="mt-1 text-sm">We couldn’t read the evidence for these clearly, so they don’t count either way yet.</p>
          <ul className="mt-3 grid gap-3">
            {review.map((skill) => <li key={skill.skill_id}>
              <details>
                <summary className="cursor-pointer font-bold">{skillLabel(skill.skill_id)}</summary>
                <div className="mt-3 rounded-lg bg-card p-3"><SkillEvidence skill={skill} report={report} /></div>
              </details>
            </li>)}
          </ul>
        </section>}
        <RankingNote run={run} role={role} />
      </aside>
    </div>
  </>;
}

function GapCard({ gap, rank, report, variant }: {
  gap: CoreSkillResult; rank: number; report: CoreSkillGapReport; variant: "lead" | "open" | "closed";
}) {
  const plan = usePlan();
  const [open, setOpen] = useState(variant !== "closed");
  const share = demandShare(gap);
  const level = demandLevel(share);
  const ways = resourcesForSkill(plan.resources, gap.skill_id);
  const shown = ways.slice(0, 3);
  const name = skillLabel(gap.skill_id);
  return (
    <section aria-labelledby={`gap-${gap.skill_id}`} className="rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h2 id={`gap-${gap.skill_id}`} className={cn("flex min-w-0 flex-1 basis-56 items-baseline gap-3", variant === "lead" ? "text-section" : "text-xl")}>
          <span className="font-mono text-sm font-normal text-muted-foreground">{String(rank).padStart(2, "0")}</span>{name}
        </h2>
        <Badge variant={level === "high" ? "warning" : "default"}>{DEMAND_LABELS[level]}</Badge>
        <span className="font-mono text-sm text-muted-foreground">In {percent(share)} of postings</span>
      </div>
      <GapBar skill={gap} className="mt-5" />
      <div className="mt-3"><GapMeta skill={gap} /></div>

      {open ? <>
        <p className="eyebrow mt-6 mb-3">Ways to close it</p>
        {plan.status === "loading" ? <p className="text-muted-foreground">Loading resources…</p>
          : shown.length === 0 ? <p className="text-muted-foreground">No resources for this skill yet.</p>
          : variant === "lead" ? <div className="grid gap-3 sm:grid-cols-3">
            {shown.map((resource) => <div key={resource.id} className="flex flex-col rounded-xl bg-sunken p-4">
              <ResourceIcon type={resource.type} />
              <p className="eyebrow mt-3">{RESOURCE_TYPES[resource.type].label}</p>
              <p className="mt-0.5 font-bold">{resource.title}</p>
              <p className="mt-1 font-mono text-[0.8125rem] text-muted-foreground">{resource.meta}</p>
              <SaveButton resourceId={resource.id} tone="tile" className="mt-auto self-start" />
            </div>)}
          </div>
          : <ul className="grid gap-3 rounded-xl bg-sunken p-4">
            {shown.map((resource) => <li key={resource.id} className="flex flex-wrap items-center gap-3">
              <ResourceIcon type={resource.type} />
              <div className="min-w-0 flex-1 basis-48">
                <p className="font-bold">{resource.title}</p>
                <p className="font-mono text-[0.8125rem] text-muted-foreground">{resource.provider} · {resource.meta}</p>
              </div>
              <SaveButton resourceId={resource.id} tone="tile" />
            </li>)}
          </ul>}
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <Link href={`/resources?gap=${gap.skill_id}`} className="inline-flex items-center gap-1 font-bold hover:underline">
            Browse all {ways.length} resources for this skill<ChevronRight aria-hidden className="size-4" />
          </Link>
        </div>
        <details className="group mt-4 border-t border-border pt-4">
          <summary className="flex cursor-pointer list-none items-center gap-1 text-sm font-bold [&::-webkit-details-marker]:hidden">
            Why this rating<ChevronDown aria-hidden className="size-4 transition-transform group-open:rotate-180" />
          </summary>
          <div className="mt-4"><SkillEvidence skill={gap} report={report} /></div>
        </details>
      </> : (
        <Button variant="outline" className="mt-5" aria-expanded={false} onClick={() => setOpen(true)}>
          Show {ways.length} ways to close it<ChevronDown data-icon="inline-end" />
        </Button>
      )}
    </section>
  );
}

function RankingNote({ run, role }: { run: SkillGapRun; role: string }) {
  const { analyze, submitting } = useSkillGapAnalysis();
  return (
    <section aria-labelledby="ranked" className="rounded-2xl bg-sunken p-6">
      <h2 id="ranked" className="text-title">How gaps are ranked</h2>
      <p className="mt-2 text-sm/6 text-muted-foreground">
        We compare the evidence in your résumé with what {role.toLowerCase()} postings ask for, then put the
        most-requested gaps first. Listing a skill counts a little; showing you used it in a project or job counts
        more. The scoring is early and uncalibrated.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" variant="raised" disabled={submitting} onClick={() => void analyze(true)}>
          <RotateCcw data-icon="inline-start" />Analyze again
        </Button>
        <Button size="sm" variant="raised" onClick={() => downloadReport(run)}><Download data-icon="inline-start" />JSON</Button>
      </div>
      <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground"><Check aria-hidden className="size-3.5" />
        Finished in {run.elapsed_seconds.toFixed(0)}s · reopening this page doesn’t rerun it</p>
    </section>
  );
}

function downloadReport(run: SkillGapRun) {
  const content = { run_id: run.id, filename: run.filename, job_family: run.job_family,
    resume_hash: run.resume_hash, completed_at: run.completed_at, match: run.match, report: run.report };
  const url = URL.createObjectURL(new Blob([JSON.stringify(content, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `careergps-skill-gaps-${run.job_family}.json`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
