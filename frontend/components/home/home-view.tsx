"use client";

import Link from "next/link";
import { ArrowRight, Bookmark, CircleDashed, Flag, LoaderCircle, MapPin } from "lucide-react";

import {
  AnalysisGate,
  GapBar,
  GapMeta,
  MatchRing,
  RESOURCE_TYPES,
  ROLE_NAMES,
  skillLabel,
} from "@/components/career/route-parts";
import { ADD_DESTINATION_HREF, FAMILIES, useDestinationRuns } from "@/components/destinations/use-destination-runs";
import { useSwitchRoute } from "@/components/layout/use-switch-route";
import { usePlan } from "@/components/plan/plan-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { orderPlan, percent, rankGaps, rankStrengths, resourcesForSkill, type PlanStep } from "@/lib/career";
import { cn } from "@/lib/utils";

export function HomeView() {
  const { snapshot, run } = useSkillGapAnalysis();
  if (run?.status !== "completed" || !run.report || !snapshot) {
    return <>
      <h1 className="mb-6 text-page-title">Your route</h1>
      <AnalysisGate />
    </>;
  }
  return <HomeReady />;
}

function HomeReady() {
  const { snapshot, family, run } = useSkillGapAnalysis();
  const plan = usePlan();
  const report = run!.report!;
  const match = run!.match?.score ?? null;
  const gaps = rankGaps(report);
  const strengths = rankStrengths(report);
  const ordered = orderPlan(plan.items, plan.resources, gaps.map((gap) => gap.skill_id));
  const total = ordered.done.length + ordered.ahead.length + ordered.alongside.length;
  const sample = report.skills[0]?.demand.N ?? null;
  const role = ROLE_NAMES[family];

  return (
    <div className="grid gap-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <section aria-labelledby="where" className="rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="min-w-0 flex-1 basis-72">
              <h1 id="where" className="text-page-title">
                {match === null ? "Your route is ready" : `You’re ${percent(match)} of the way there`}
              </h1>
              <p className="mt-2 text-base/7 text-muted-foreground">
                Matched with {snapshot!.filename}{sample ? ` against ${sample.toLocaleString()} ${role.toLowerCase()} postings` : ""}.
              </p>
            </div>
            <MatchRing value={match} size={120} stroke={12} />
          </div>
          <RouteTrack value={match ?? 0} start={`Résumé confirmed ${shortDate(snapshot!.confirmed_at)}`} goal={role} />
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <Tile value={String(gaps.length)} label={gaps.length === 1 ? "gap left" : "gaps left"} />
            <Tile value={`${ordered.done.length} of ${total}`} label="plan steps done" />
            <Tile value={String(strengths.length)} label={strengths.length === 1 ? "strength" : "strengths"} />
          </div>
        </section>

        <div className="grid content-start gap-6">
          <NextTurn next={ordered.ahead[0] ?? ordered.alongside[0] ?? null} topGap={gaps[0]?.skill_id ?? null} />
          <section aria-labelledby="then" className="rounded-2xl border border-border bg-card p-6 shadow-card">
            <h2 id="then" className="text-title">Then on your plan</h2>
            {plan.status === "loading" ? <p className="mt-3 text-muted-foreground">Loading your plan…</p>
              : total === 0 ? <p className="mt-3 text-muted-foreground">Save resources and they’ll appear here in the order to do them.</p>
              : <ul className="mt-3 grid gap-3">
                {ordered.ahead.slice(1, 3).map((step) => <PlanLine key={step.resource.id} step={step} />)}
                {ordered.alongside.slice(0, 2).map((step) => <PlanLine key={step.resource.id} step={step} alongside />)}
              </ul>}
            {total > 0 && <p className="mt-4 text-sm text-muted-foreground">{ordered.done.length} of {total} steps done</p>}
          </section>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="gapsnap" className="rounded-2xl border border-border bg-card p-6 shadow-card">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="gapsnap" className="text-title">Gaps · {gaps.length} left</h2>
            <Link href="/gaps" className="text-sm font-bold hover:underline">See gaps</Link>
          </div>
          {gaps.length ? <ul className="mt-4 grid gap-5">
            {gaps.slice(0, 3).map((gap) => <li key={gap.skill_id} className="grid gap-2">
              <p className="font-bold">{skillLabel(gap.skill_id)}</p>
              <GapBar skill={gap} />
              <GapMeta skill={gap} />
            </li>)}
          </ul> : <p className="mt-3 text-muted-foreground">No gaps left for this role. Your résumé shows strong evidence for every skill postings ask for.</p>}
        </section>
        <ResourceSnapshot gaps={gaps.slice(0, 3).map((gap) => gap.skill_id)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Destinations />
        <section aria-labelledby="about" className="rounded-2xl bg-sunken p-6">
          <h2 id="about" className="text-title">How your match works</h2>
          <p className="mt-2 text-sm/6 text-muted-foreground">
            Each skill counts as much as postings ask for it. Strong evidence in your résumé moves you forward; listing a
            skill counts a little, and doing it in a project or job counts more. Skills we couldn’t read clearly
            {run!.match?.unscored_skill_count ? ` (${run!.match.unscored_skill_count} right now)` : ""} are left out until
            you review them. It’s an early, uncalibrated score, not a hiring prediction.
          </p>
        </section>
      </div>
    </div>
  );
}

function RouteTrack({ value, start, goal }: { value: number; start: string; goal: string }) {
  const at = Math.min(96, Math.max(4, value * 100));
  return (
    <div className="mt-8">
      <div aria-hidden className="relative h-11">
        <span className="absolute top-1/2 left-0 size-3.5 -translate-y-1/2 rounded-full bg-foreground" />
        <span className="absolute top-1/2 left-1 h-1.5 -translate-y-1/2 rounded-full bg-foreground" style={{ width: `${at}%` }} />
        <span className="absolute top-1/2 right-5 border-t-2 border-dashed border-line-strong" style={{ left: `${at}%` }} />
        <span className="absolute top-1/2 grid size-10 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-foreground bg-accent" style={{ left: `${at}%` }}>
          <MapPin className="size-4.5" />
        </span>
        <span className="absolute top-1/2 right-0 grid size-10 -translate-y-1/2 place-items-center rounded-full border border-line-strong bg-card">
          <Flag className="size-4.5" />
        </span>
      </div>
      <div className="mt-3 flex justify-between gap-4 text-sm">
        <span className="text-muted-foreground">{start}</span>
        <span className="text-right font-bold">{goal}</span>
      </div>
    </div>
  );
}

function Tile({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-lg bg-sunken px-4 py-3.5">
      <p className="font-mono text-xl font-medium">{value}</p>
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}

function NextTurn({ next, topGap }: { next: PlanStep | null; topGap: string | null }) {
  const plan = usePlan();
  return (
    <section aria-labelledby="next" className="rounded-2xl border-2 border-foreground bg-card p-6 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <Badge variant="brand">Next turn</Badge>
        <Link href="/plan" className="text-sm font-bold hover:underline">Action plan</Link>
      </div>
      {plan.status === "loading" ? <p className="mt-4 text-muted-foreground">Loading your plan…</p>
        : next ? <>
          <h2 id="next" className="mt-4 text-[1.375rem]/8">{next.resource.title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {RESOURCE_TYPES[next.resource.type].label}{next.skill && <> · closes <b className="text-foreground">{skillLabel(next.skill)}</b></>}
          </p>
          <Button asChild size="lg" className="mt-5">
            {next.resource.url
              ? <a href={next.resource.url} target="_blank" rel="noreferrer">Start this step<ArrowRight data-icon="inline-end" /></a>
              : <Link href="/plan">Start this step<ArrowRight data-icon="inline-end" /></Link>}
          </Button>
        </> : <>
          <h2 id="next" className="mt-4 text-[1.375rem]/8">
            {topGap ? `Pick a way to close ${skillLabel(topGap)}` : "Pick your next step"}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">Save a course, project or club and it becomes your next turn.</p>
          <Button asChild size="lg" className="mt-5">
            <Link href={topGap ? `/resources?gap=${topGap}` : "/resources"}>Browse resources<ArrowRight data-icon="inline-end" /></Link>
          </Button>
        </>}
    </section>
  );
}

function PlanLine({ step, alongside = false }: { step: PlanStep; alongside?: boolean }) {
  return (
    <li className="flex items-start gap-3">
      {alongside ? <CircleDashed aria-hidden className="mt-1 size-4 shrink-0 text-muted-foreground" />
        : <span aria-hidden className="mt-1.5 size-3 shrink-0 rounded-full border-2 border-line-strong" />}
      <span className="font-bold">{step.resource.title}{alongside && <span className="font-normal text-muted-foreground"> · alongside</span>}</span>
    </li>
  );
}

function ResourceSnapshot({ gaps }: { gaps: string[] }) {
  const plan = usePlan();
  const forGaps = new Map(gaps.flatMap((gap) => resourcesForSkill(plan.resources, gap)).map((r) => [r.id, r]));
  const unsaved = [...forGaps.values()].filter((resource) => !plan.saved.has(resource.id));
  return (
    <section aria-labelledby="ressnap" className="rounded-2xl border border-border bg-card p-6 shadow-card">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="ressnap" className="text-title">Resources</h2>
        <Link href="/resources" className="text-sm font-bold hover:underline">Browse all</Link>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-accent px-4 py-3.5">
          <p className="font-mono text-xl font-medium">{plan.items.length}</p><p className="text-sm">saved to plan</p>
        </div>
        <div className="rounded-lg bg-sunken px-4 py-3.5">
          <p className="font-mono text-xl font-medium">{unsaved.length}</p><p className="text-sm text-muted-foreground">more for your top gaps</p>
        </div>
      </div>
      {plan.status === "error" && <p role="alert" className="mt-3 text-sm text-destructive">{plan.error}</p>}
      <ul className="mt-3 grid gap-3">
        {unsaved.slice(0, 2).map((resource) => (
          <li key={resource.id} className="flex items-center gap-3 rounded-lg bg-sunken px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="truncate font-bold">{resource.title}</p>
              <p className="truncate text-sm text-muted-foreground">{resource.provider} · {skillLabel(resource.skills.find((s) => gaps.includes(s)) ?? resource.skills[0])}</p>
            </div>
            <Button size="icon-sm" variant="raised" aria-label={`Save ${resource.title} to plan`}
              disabled={plan.pending.has(resource.id)} onClick={() => void plan.setStatus(resource.id, "saved")}>
              {plan.pending.has(resource.id) ? <LoaderCircle className="motion-safe:animate-spin" /> : <Bookmark />}
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Destinations() {
  const { families, runs } = useDestinationRuns();
  const { family, locked, switchTo } = useSwitchRoute();
  return (
    <section aria-labelledby="dest" className="rounded-2xl border border-border bg-card p-6 shadow-card">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="dest" className="text-title">Your destinations</h2>
        <Link href="/destinations" className="text-sm font-bold hover:underline">Manage</Link>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {families.map((key) => {
          const { status, run } = runs[key];
          const value = run?.status === "completed" ? run.match?.score ?? null : null;
          return (
            <button key={key} type="button" disabled={locked && key !== family} onClick={() => void switchTo(key)}
              aria-pressed={key === family}
              className={cn("grid gap-1 rounded-xl border border-border px-4 py-3.5 text-left transition-colors hover:bg-background disabled:opacity-60",
                key === family && "border-2 border-foreground")}>
              <span className="flex items-baseline justify-between gap-2">
                <b>{ROLE_NAMES[key]}</b>
                <span className="font-mono">{value === null ? "" : percent(value)}</span>
              </span>
              <span className="text-sm text-muted-foreground">
                {status === "loading" ? "Loading…" : value !== null ? (key === family ? "Selected" : "Select")
                  : run && run.status !== "failed" ? "Analyzing…" : "Not analyzed yet"}
              </span>
            </button>
          );
        })}
        {families.length < FAMILIES.length && (
          <Link href={ADD_DESTINATION_HREF}
            className="grid place-content-center rounded-xl border border-dashed border-line-strong px-4 py-3.5 text-center font-bold transition-colors hover:bg-background">
            + Add a destination
          </Link>
        )}
      </div>
    </section>
  );
}

function shortDate(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
