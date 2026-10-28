"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, CircleCheck, Flag, LoaderCircle, Plus, RotateCcw, X } from "lucide-react";

import {
  MatchRing,
  RESOURCE_TYPES,
  ROLE_NAMES,
  ResourceIcon,
  RoutePageHeader,
  skillLabel,
} from "@/components/career/route-parts";
import { usePlan } from "@/components/plan/plan-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { orderPlan, rankGaps, type OrderedPlan, type PlanStep } from "@/lib/career";
import { cn } from "@/lib/utils";

export function PlanView() {
  const { family, run, snapshot, loaded, error } = useSkillGapAnalysis();
  const plan = usePlan();
  const [view, setView] = useState<"flowchart" | "list">("flowchart");
  const report = run?.status === "completed" ? run.report : null;
  const gaps = report ? rankGaps(report).map((gap) => gap.skill_id) : [];
  const ordered = orderPlan(plan.items, plan.resources, gaps);
  const total = ordered.done.length + ordered.ahead.length + ordered.alongside.length;
  const next = ordered.ahead[0] ?? null;
  const role = ROLE_NAMES[family];

  return <>
    <RoutePageHeader title="What to do, in order"
      description={total ? `Built from the ${total} resources you saved. Biggest gaps first, then everything that builds on them.`
        : "Save resources and we’ll put them in the best order."}
      aside={<div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label="View" className="flex rounded-full bg-sunken p-1">
          {(["flowchart", "list"] as const).map((key) => (
            <button key={key} type="button" aria-pressed={view === key} onClick={() => setView(key)}
              className={cn("h-9 rounded-full px-4 text-sm font-bold text-muted-foreground capitalize",
                view === key && "bg-card text-foreground shadow-card")}>{key}</button>
          ))}
        </div>
        <Button asChild variant="outline" size="lg"><Link href="/resources"><Plus data-icon="inline-start" />Add resources</Link></Button>
      </div>} />

    {!loaded || plan.status === "loading" ? <p role="status" className="flex items-center gap-2 text-muted-foreground"><LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />Loading your plan…</p>
      // No snapshot because the profile couldn't be loaded, not because there's no résumé.
      : !snapshot && error ? <p role="alert" className="rounded-2xl bg-danger-soft p-6">{error}</p>
      : !snapshot ? <p className="rounded-2xl border border-border bg-card p-6">Upload your résumé first. <Link href="/onboarding" className="font-bold underline">Upload résumé</Link></p>
      : plan.status === "error" ? <p role="alert" className="rounded-2xl bg-danger-soft p-6">{plan.error}</p>
      : total === 0 ? <div className="grid justify-items-center gap-3 rounded-2xl border border-border bg-card px-6 py-14 text-center">
        <h2 className="text-section">Your plan is empty</h2>
        <p className="max-w-md text-muted-foreground">Save a few courses, projects or clubs that close your gaps. We’ll order them so the biggest gap comes first.</p>
        <Button asChild size="lg" className="mt-2"><Link href={gaps[0] ? `/resources?gap=${gaps[0]}` : "/resources"}>Browse resources<ArrowRight data-icon="inline-end" /></Link></Button>
      </div>
      : <div className="grid gap-6">
        {plan.actionError && <p role="alert" className="text-sm text-destructive">{plan.actionError}</p>}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex items-center gap-4 rounded-2xl border border-border bg-card px-6 py-5 shadow-card">
            <MatchRing value={ordered.done.length / total} size={52} stroke={6} label={null} className="[&_p]:hidden" />
            <div><p className="font-mono text-xl font-medium">{ordered.done.length} of {total}</p><p className="text-sm text-muted-foreground">steps done</p></div>
          </div>
          <div className="rounded-2xl border border-border bg-card px-6 py-5 shadow-card">
            <p className="eyebrow">Next turn</p>
            {next ? <>
              <p className="mt-1 font-bold">{next.resource.title}</p>
              <p className="text-sm text-muted-foreground">{next.skill ? `Closes ${skillLabel(next.skill)}` : RESOURCE_TYPES[next.resource.type].label}</p>
            </> : <p className="mt-1 font-bold">{ordered.alongside.length ? "Keep up your ongoing steps" : "Every saved step is done"}</p>}
          </div>
        </div>

        {view === "flowchart" ? <Flowchart ordered={ordered} role={role} /> : <PlanList ordered={ordered} />}

        <div className="grid gap-4 md:grid-cols-2">
          <section aria-labelledby="why" className="rounded-2xl bg-sunken p-6">
            <h2 id="why" className="text-title">How we ordered this</h2>
            <p className="mt-2 text-sm/6 text-muted-foreground">
              {next?.skill ? `${skillLabel(next.skill)} is the biggest gap you saved a step for, so it comes first. ` : ""}
              After that, steps follow your gap ranking. Within one gap, projects and courses come before the
              certifications they prepare you for. Clubs and meetups run alongside everything else.
            </p>
          </section>
          <section aria-labelledby="change" className="rounded-2xl border border-border bg-card p-6 shadow-card">
            <h2 id="change" className="text-title">Want a different order?</h2>
            <p className="mt-2 text-sm/6 text-muted-foreground">Mark steps done as you go, or remove the ones you won’t do. Save others from Resources and they slot in by gap.</p>
            <Link href="/resources" className="mt-3 inline-block font-bold underline">Manage saved resources</Link>
          </section>
        </div>
      </div>}
  </>;
}

function Flowchart({ ordered, role }: { ordered: OrderedPlan; role: string }) {
  const [next, ...later] = ordered.ahead;
  const nodes: { step: PlanStep; state: "done" | "next" | "ahead"; label: string }[] = [
    ...ordered.done.map((step) => ({ step, state: "done" as const, label: `Done · ${shortDate(step.item.done_at)}` })),
    ...(next ? [{ step: next, state: "next" as const, label: "Now" }] : []),
    ...later.map((step, index) => ({ step, state: "ahead" as const, label: `Step ${ordered.done.length + index + 2}` })),
  ];
  return (
    <section aria-labelledby="chart" className="rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 id="chart" className="text-section">Your route, step by step</h2>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-2"><span aria-hidden className="w-6 border-t-2 border-foreground" />Done</span>
          <span className="inline-flex items-center gap-2"><span aria-hidden className="w-6 border-t-2 border-dashed border-line-strong" />Ahead</span>
          <span className="inline-flex items-center gap-2"><span aria-hidden className="size-3.5 rounded-sm border border-dashed border-line-strong" />Runs alongside</span>
        </p>
      </div>

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
        <div>
          <p className="eyebrow mb-4 sm:ml-24">Main path</p>
          <ol className="grid">
            {nodes.map(({ step, state, label }, index) => (
              <li key={step.resource.id} className="grid sm:grid-cols-[6rem_minmax(0,1fr)]">
                <span className={cn("hidden pt-5 pr-4 text-right font-mono text-sm sm:block", state === "next" ? "font-sans font-bold" : "text-muted-foreground")}>{label}</span>
                <div>
                  {index > 0 && <Connector solid={state === "done"} />}
                  <PlanNode step={step} state={state} label={label} />
                </div>
              </li>
            ))}
            <li className="grid sm:grid-cols-[6rem_minmax(0,1fr)]">
              <span className="hidden pt-5 pr-4 text-right font-mono text-sm text-muted-foreground sm:block">Goal</span>
              <div>
                {nodes.length > 0 && <Connector solid={false} />}
                <div className="flex items-center gap-4 rounded-xl bg-deep px-6 py-5 text-deep-foreground">
                  <Flag aria-hidden className="size-5 shrink-0 text-accent" />
                  <div><p className="text-title">Destination: {role}</p><p className="text-sm text-deep-muted">Ready to apply for {role.toLowerCase()} roles</p></div>
                </div>
              </div>
            </li>
          </ol>
        </div>

        <div>
          <p className="eyebrow mb-4">Alongside</p>
          {ordered.alongside.length ? <ul className="grid gap-4">
            {ordered.alongside.map((step) => <li key={step.resource.id}><PlanNode step={step} state="alongside" label="Alongside" /></li>)}
            <li className="text-sm text-muted-foreground">Keep going weekly while you work through the main path.</li>
          </ul> : <p className="rounded-xl border border-dashed border-line-strong p-5 text-sm text-muted-foreground">
            Clubs and meetups you save run here, next to the main path. <Link href="/resources" className="font-bold text-foreground underline">Find one</Link>
          </p>}
        </div>
      </div>
    </section>
  );
}

function Connector({ solid }: { solid: boolean }) {
  return <div aria-hidden className="flex h-10 justify-center">
    <span className={cn("h-full border-l-2", solid ? "border-foreground" : "border-dashed border-line-strong")} />
  </div>;
}

function PlanNode({ step, state, label }: { step: PlanStep; state: "done" | "next" | "ahead" | "alongside"; label: string }) {
  const plan = usePlan();
  const { resource } = step;
  const busy = plan.pending.has(resource.id);
  const kind = RESOURCE_TYPES[resource.type].label;
  const closes = step.skill ? `closes ${skillLabel(step.skill)}` : "";
  return (
    <div className={cn("group/node relative rounded-xl p-5",
      state === "done" && "bg-sunken",
      state === "next" && "border-2 border-foreground bg-card",
      state === "ahead" && "border border-border bg-card",
      state === "alongside" && "border border-dashed border-line-strong bg-card")}>
      <p className="sr-only sm:hidden">{label}</p>
      <div className="flex items-start gap-3">
        {state === "done" ? <CircleCheck aria-hidden className="mt-0.5 size-5 shrink-0 text-success" />
          : state !== "next" && <ResourceIcon type={resource.type} className="size-8 bg-sunken" />}
        <div className="min-w-0 flex-1">
          {state === "next" && <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge variant="brand">Next turn</Badge><span className="eyebrow">{kind} · {resource.meta}</span>
          </div>}
          <p className={cn("font-bold", state === "next" && "text-[1.375rem]/8")}>{resource.title}</p>
          <p className="text-sm text-muted-foreground">{state === "next" ? (step.skill ? <>Closes <b className="text-foreground">{skillLabel(step.skill)}</b></> : kind)
            : [kind, state === "done" ? "" : resource.meta, closes].filter(Boolean).join(" · ")}</p>
        </div>
        {state !== "next" && <Button size="icon-xs" variant="ghost" aria-label={`Remove ${resource.title} from plan`} disabled={busy}
          onClick={() => void plan.remove(resource.id)} className="opacity-60 hover:opacity-100"><X /></Button>}
      </div>
      <div className={cn("flex flex-wrap gap-2", state === "next" ? "mt-5" : "mt-3 sm:ml-11")}>
        {state === "next" && resource.url && <Button asChild>
          <a href={resource.url} target="_blank" rel="noreferrer">Start this step<ArrowRight data-icon="inline-end" /></a>
        </Button>}
        {state === "done"
          ? <Button size="xs" variant="raised" disabled={busy} onClick={() => void plan.setStatus(resource.id, "saved")}><RotateCcw data-icon="inline-start" />Not done</Button>
          : <Button size={state === "next" ? "default" : "xs"} variant={state === "next" ? "outline" : "secondary"} disabled={busy}
            onClick={() => void plan.setStatus(resource.id, "done")}>
            {busy ? <LoaderCircle data-icon="inline-start" className="motion-safe:animate-spin" /> : <Check data-icon="inline-start" />}Mark done
          </Button>}
        {state === "next" && <Button variant="ghost" disabled={busy} onClick={() => void plan.remove(resource.id)}>Remove</Button>}
      </div>
    </div>
  );
}

function PlanList({ ordered }: { ordered: OrderedPlan }) {
  const plan = usePlan();
  const rows = [...ordered.ahead, ...ordered.alongside, ...ordered.done];
  return (
    <section aria-label="Plan steps" className="rounded-2xl border border-border bg-card shadow-card">
      <ol className="divide-y divide-border">
        {rows.map((step) => {
          const done = step.item.status === "done";
          const busy = plan.pending.has(step.resource.id);
          return (
            <li key={step.resource.id} className="flex flex-wrap items-center gap-3 px-5 py-4 sm:px-6">
              <input type="checkbox" checked={done} disabled={busy} aria-label={`${step.resource.title} done`}
                onChange={() => void plan.setStatus(step.resource.id, done ? "saved" : "done")}
                className="size-5 shrink-0 accent-foreground" />
              <div className="min-w-0 flex-1 basis-56">
                <p className={cn("font-bold", done && "text-muted-foreground line-through")}>{step.resource.title}</p>
                <p className="text-sm text-muted-foreground">
                  {[RESOURCE_TYPES[step.resource.type].label, step.resource.alongside ? "alongside" : "",
                    step.skill ? `closes ${skillLabel(step.skill)}` : ""].filter(Boolean).join(" · ")}
                </p>
              </div>
              {step.resource.url && <Button asChild size="sm" variant="secondary"><a href={step.resource.url} target="_blank" rel="noreferrer">Open</a></Button>}
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => void plan.remove(step.resource.id)}>Remove</Button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function shortDate(iso: string | null) {
  const date = iso ? new Date(iso) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
}
