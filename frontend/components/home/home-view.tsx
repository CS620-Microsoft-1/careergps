"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, ChevronRight, Flag, MapPin, Plus } from "lucide-react";

import {
  AnalysisGate,
  GapBar,
  GapMeta,
  MatchRing,
  ROLE_NAMES,
  SourceNote,
  skillLabel,
} from "@/components/career/route-parts";
import { ADD_DESTINATION_HREF, FAMILIES, useDestinationRuns } from "@/components/destinations/use-destination-runs";
import { useAccount } from "@/components/layout/account-provider";
import { useSwitchRoute } from "@/components/layout/use-switch-route";
import { usePlan } from "@/components/plan/plan-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { orderPlan, percent, rankGaps, type PlanStep } from "@/lib/career";
import { cn } from "@/lib/utils";

export function HomeView() {
  const { snapshot, run } = useSkillGapAnalysis();
  const ready = run?.status === "completed" && !!run.report && !!snapshot;
  /** "left" once the page has gone back to the gate (a destination switch), so its return eases in but the first load doesn't. */
  const [seen, setSeen] = useState<"no" | "ready" | "left">("no");
  if (ready && seen === "no") setSeen("ready");
  if (!ready && seen === "ready") setSeen("left");
  if (!ready) {
    // Held back a beat so a quick load never flashes the gate.
    return <div className="entrance-rise [--enter-ms:200ms] [animation-delay:150ms]">
      <h1 className="mb-6 text-page-title">Your route</h1>
      <AnalysisGate />
    </div>;
  }
  return <HomeReady entering={seen === "left"} />;
}

function HomeReady({ entering }: { entering: boolean }) {
  const { snapshot, family, run } = useSkillGapAnalysis();
  const { user } = useAccount();
  const plan = usePlan();
  const report = run!.report!;
  const match = run!.match?.score ?? null;
  const gaps = rankGaps(report);
  const ordered = orderPlan(plan.items, plan.resources, gaps.map((gap) => gap.skill_id));
  const sample = report.skills[0]?.demand.N ?? null;
  const role = ROLE_NAMES[family];
  const location = user?.preferred_location;

  return (
    <div className={cn("grid gap-12", entering && "entrance-rise [--enter-ms:200ms]")}>
      <div className="grid gap-6 lg:grid-cols-12">
        <section aria-labelledby="where" className="flex flex-col gap-6 rounded-3xl border border-border bg-card p-6 shadow-card sm:p-8 lg:col-span-7">
          <div className="grid gap-2">
            <p className="eyebrow">Your goal · {role}{location ? ` · ${location}` : ""}</p>
            <h1 id="where" className="text-page-title">
              {match === null ? "Your route is ready" : `You’re ${percent(match)} of the way there`}
            </h1>
            <p className="text-base/7 text-muted-foreground">
              Matched with {snapshot!.filename}{sample ? ` against ${sample.toLocaleString()} ${role.toLowerCase()} postings` : ""}.
            </p>
          </div>
          <RouteTrack value={match ?? 0} start={`Résumé confirmed ${shortDate(snapshot!.confirmed_at)}`} goal={role} />
          {/* Pinned to the bottom when Next turn makes the row taller. */}
          <div className="mt-auto">
            <OtherDestinations />
          </div>
        </section>

        <NextTurn next={ordered.ahead[0] ?? ordered.alongside[0] ?? null} topGap={gaps[0]?.skill_id ?? null} />
      </div>

      <section aria-labelledby="gaps" className="grid gap-6 rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 id="gaps" className="text-title">Skills to build</h2>
          <Link href="/gaps" className="text-sm font-bold hover:underline">See all gaps</Link>
        </div>
        {gaps.length ? <ul className="grid gap-8 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
          {gaps.slice(0, 3).map((gap) => <li key={gap.skill_id}>
            <Link href={`/resources?gap=${gap.skill_id}`} aria-label={`Ways to close the ${skillLabel(gap.skill_id)} gap`}
              className="group -m-3 grid gap-2 rounded-lg p-3 pressable hover:bg-background motion-safe:active:scale-[0.98]">
              <span className="font-bold">{skillLabel(gap.skill_id)}</span>
              <GapBar skill={gap} />
              <GapMeta skill={gap} />
              <span className="inline-flex items-center gap-1 justify-self-start font-bold group-hover:underline">
                See ways to close it<ChevronRight aria-hidden className="size-4" />
              </span>
            </Link>
          </li>)}
        </ul> : <p className="text-muted-foreground">No gaps left for this role. Your résumé shows strong evidence for every skill postings ask for.</p>}
        {sample && <SourceNote>Based on {sample.toLocaleString()} job postings for this role.</SourceNote>}
      </section>
    </div>
  );
}

function RouteTrack({ value, start, goal }: { value: number; start: string; goal: string }) {
  const at = Math.min(96, Math.max(4, value * 100));
  return (
    <div>
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

function NextTurn({ next, topGap }: { next: PlanStep | null; topGap: string | null }) {
  const plan = usePlan();
  // Only when the plan was still loading as the card appeared: its content fades in instead of popping.
  const [waited] = useState(plan.status === "loading");
  const body = cn("flex flex-1 flex-col gap-3", waited && "entrance-fade [--enter-ms:200ms]");
  return (
    <section aria-labelledby="next" className="flex flex-col gap-3 rounded-2xl border-2 border-foreground bg-card p-6 shadow-card sm:p-8 lg:col-span-5">
      <Badge variant="brand" className="self-start">Next turn</Badge>
      {plan.status === "loading" ? <p className="text-muted-foreground">Loading your plan…</p>
        : next ? <div className={body}>
          <h2 id="next" className="text-[2rem]/11 font-bold tracking-[-0.01em]">{next.resource.title}</h2>
          {next.skill && <p className="text-muted-foreground">Closes <b className="text-foreground">{skillLabel(next.skill)}</b></p>}
          {next.resource.description && <p className="text-lg/7.5 text-muted-foreground">{next.resource.description}</p>}
          <div className="mt-auto flex flex-wrap items-center gap-6 pt-2">
            <Button asChild size="lg">
              {next.resource.url
                ? <a href={next.resource.url} target="_blank" rel="noreferrer">Start this step<ArrowRight data-icon="inline-end" /></a>
                : <Link href="/plan">Start this step<ArrowRight data-icon="inline-end" /></Link>}
            </Button>
            <Link href="/plan" className="font-bold hover:underline">See action plan</Link>
          </div>
        </div> : <div className={body}>
          <h2 id="next" className="text-[2rem]/11 font-bold tracking-[-0.01em]">Your plan is empty</h2>
          <p className="text-lg/7.5 text-muted-foreground">
            {topGap ? <>Add a resource for <b className="text-foreground">{skillLabel(topGap)}</b> to get your first step.</>
              : "Add a resource for one of your gaps to get your first step."}
          </p>
          <div className="mt-auto pt-2">
            <Button asChild size="lg">
              <Link href={topGap ? `/resources?gap=${topGap}` : "/resources"}>Add resources<ArrowRight data-icon="inline-end" /></Link>
            </Button>
          </div>
        </div>}
    </section>
  );
}

function OtherDestinations() {
  const { families, resumes, runs, listed } = useDestinationRuns();
  const { family, locked, switchTo } = useSwitchRoute();
  const others = families.filter((key) => key !== family);
  // Held until the list and every score are in, so the rows fade in once instead of popping in one by one.
  const settled = listed && others.every((key) => runs[key].status !== "loading");
  const [waited] = useState(!settled);
  return (
    <div className="grid gap-2">
      <p className="eyebrow">Your other destinations</p>
      {!settled ? <div aria-hidden className="h-20" /> : <div className={cn("flex flex-wrap gap-3", waited && "entrance-fade [--enter-ms:200ms]")}>
        {others.map((key) => {
          const { run } = runs[key];
          const value = run?.status === "completed" ? run.match?.score ?? null : null;
          return (
            <button key={key} type="button" disabled={locked} onClick={() => void switchTo(key)}
              className="flex min-w-0 flex-[1_1_220px] items-center gap-3 rounded-lg bg-sunken px-4 py-3 text-left pressable hover:bg-secondary enabled:motion-safe:active:scale-[0.98] disabled:opacity-60">
              <MatchRing value={value} size={56} stroke={6} label={null} />
              <span className="flex min-w-0 flex-col">
                <b>{ROLE_NAMES[key]}</b>
                <span className="truncate text-sm text-muted-foreground">
                  {value !== null ? resumes[key]?.original_filename ?? "Your résumé"
                    : run && run.status !== "failed" ? "Analyzing…" : "Not analyzed yet"}
                </span>
              </span>
            </button>
          );
        })}
        {/* With every role added there's nothing new to add, so it opens Destinations to compare them. */}
        <Link href={families.length < FAMILIES.length ? ADD_DESTINATION_HREF : "/destinations"}
          className="flex min-w-0 flex-[1_1_220px] items-center gap-3 rounded-lg border border-dashed border-line-strong px-4 py-3 pressable hover:bg-background motion-safe:active:scale-[0.98]">
          <span aria-hidden className="grid size-14 shrink-0 place-items-center rounded-full bg-sunken"><Plus className="size-5" /></span>
          <span className="flex min-w-0 flex-col">
            <b>Explore more destinations</b>
            <span className="text-sm text-muted-foreground">Find another role to compare</span>
          </span>
        </Link>
      </div>}
    </div>
  );
}

function shortDate(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
