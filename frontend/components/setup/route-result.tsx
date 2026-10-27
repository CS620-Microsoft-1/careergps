"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";

import { AnalysisGate, GapBar, GapLegend, GapMeta, MatchRing, ROLE_NAMES, SourceNote, skillLabel } from "@/components/career/route-parts";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Button } from "@/components/ui/button";
import { percent, rankGaps, rankStrengths } from "@/lib/career";
import { cn } from "@/lib/utils";

const NEXT_STEPS = [
  { title: "Browse resources for your gaps", detail: "Courses, student orgs, certifications and projects matched to each gap" },
  { title: "Save the ones you’ll actually do", detail: "Saved resources go straight into your plan" },
  { title: "Follow your action plan", detail: "We put them in order, biggest gaps first" },
];

/** After setup: the first match and the biggest gaps, while or once the analysis runs. */
export function RouteResult() {
  const router = useRouter();
  const { family, run } = useSkillGapAnalysis();
  const role = ROLE_NAMES[family];
  const report = run?.status === "completed" ? run.report : null;

  return (
    <div className="mx-auto flex w-full max-w-300 flex-1 flex-col px-4 py-6 sm:px-6">
      {!report ? (
        <div className="grid flex-1 place-items-center"><div className="w-full max-w-3xl"><AnalysisGate /></div></div>
      ) : <ReadyRoute role={role} />}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        {/* Back to the setup step that led here: the résumé review, or Add a destination. */}
        <Button variant="ghost" size="lg" onClick={() => router.back()}>Back</Button>
        <Button asChild size="lg"><Link href="/dashboard">Go to my home page<ArrowRight data-icon="inline-end" /></Link></Button>
      </div>
    </div>
  );
}

function ReadyRoute({ role }: { role: string }) {
  const { run } = useSkillGapAnalysis();
  const report = run!.report!;
  const match = run!.match?.score ?? null;
  const gaps = rankGaps(report);
  const strengths = rankStrengths(report).slice(0, 2).map((skill) => skillLabel(skill.skill_id));
  const sample = report.skills[0]?.demand.N;
  const start = strengths.length === 2 ? `${strengths[0]} and ${strengths[1]} give you a strong start.`
    : strengths.length === 1 ? `${strengths[0]} gives you a strong start.` : "Your résumé gives you a starting point.";
  const ahead = gaps.length === 0 ? "No gaps stand between you and the role."
    : `${gaps.length} ${gaps.length === 1 ? "gap stands" : "gaps stand"} between you and the role.`;

  return <>
    <div className="flex flex-col items-center gap-4 text-center sm:flex-row sm:gap-8 sm:text-left">
      <MatchRing value={match} size={120} stroke={12} />
      <div className="grid gap-2">
        <h1 className="max-w-3xl text-page-title">
          {match === null ? `Your route to ${role}` : `You’re ${percent(match)} of the way to ${role}`}
        </h1>
        <p className="max-w-2xl text-base/7 text-muted-foreground">{start} {ahead}</p>
        {sample && <SourceNote>Based on {sample.toLocaleString()} {role.toLowerCase()} job postings in the current market snapshot</SourceNote>}
      </div>
    </div>

    <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <section aria-labelledby="gaps" className="rounded-2xl border border-border bg-card p-6 shadow-card">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id="gaps" className="text-section">Biggest gaps</h2>
          <span className="eyebrow">By demand</span>
        </div>
        {gaps.length ? <ul className="mt-4 grid gap-4">
          {gaps.slice(0, 3).map((gap) => <li key={gap.skill_id} className="grid gap-2">
            <p className="font-bold">{skillLabel(gap.skill_id)}</p><GapBar skill={gap} /><GapMeta skill={gap} />
          </li>)}
        </ul> : <p className="mt-4 text-muted-foreground">Your résumé shows strong evidence for every skill postings ask for.</p>}
        <div className="mt-4"><GapLegend /></div>
      </section>

      <section aria-labelledby="nextup">
        <h2 id="nextup" className="text-section">What happens next</h2>
        <p className="mt-1 text-muted-foreground">Three steps from here to a plan you can follow.</p>
        <ol className="mt-4 grid gap-3">
          {NEXT_STEPS.map((step, index) => (
            <li key={step.title} className="flex items-center gap-4 rounded-2xl border border-border bg-card px-5 py-4 shadow-card">
              <span aria-hidden className={cn("grid size-9 shrink-0 place-items-center rounded-full font-bold", index === 0 ? "bg-accent" : "bg-sunken")}>{index + 1}</span>
              <div><p className="font-bold">{step.title}</p><p className="text-sm/6 text-muted-foreground">{step.detail}</p></div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  </>;
}
