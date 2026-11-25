"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { Check, ChevronDown, CircleCheck, LoaderCircle, Plus, RotateCcw, X } from "lucide-react";

import { RESOURCE_TYPES, ResourceIcon, skillLabel } from "@/components/career/route-parts";
import { type SuggestedEntries, usePlan } from "@/components/plan/plan-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PlanBuilding } from "@/components/plan/plan-building";
import { streamActionPlanSuggestions } from "@/lib/api/action-plans";
import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import type { ActionPlan, ActionPlanBuildStage, ActionPlanItem, ActionPlanSuggestions, JobFamily, Resource } from "@/types/api";

type State =
  | { status: "loading"; stages: ActionPlanBuildStage[] }
  | { status: "ready"; suggestions: ActionPlanSuggestions }
  | { status: "error"; message: string };

const names = (skillIds: string[]) => skillIds.map(skillLabel).join(", ");
/** A stagger delay, applied only when motion is allowed (see the motion-safe:[animation-delay] classes). */
const delay = (ms: number) => ({ "--delay": `${ms}ms` }) as React.CSSProperties;
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** "Add all" keeps the plan's order; a card added on its own slots in by gap like any saved resource. */
const entriesFor = (plan: ActionPlan): SuggestedEntries => ({
  steps: plan.steps.map((item) => item.resource_id),
  alongside: plan.alongside.map((item) => item.resource_id),
});

/**
 * An optional suggested plan on the Action plan page. It asks the backend once when it opens; nothing in
 * the saved plan changes until the student adds a card or clicks "Add all to my plan".
 * gapOrder: the student's gaps, biggest first (rankGaps), to order the skills strip.
 */
export function SuggestedPlan({ family, gapOrder, onClose }: {
  family: JobFamily; gapOrder: string[]; onClose: () => void;
}) {
  const plan = usePlan();
  const [state, setState] = useState<State>({ status: "loading", stages: [] });
  const [adding, setAdding] = useState(false);
  const controller = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setState({ status: "loading", stages: [] });
    const onStage = (stage: ActionPlanBuildStage) => {
      if (!current.signal.aborted) {
        setState((previous) => previous.status === "loading" ? { ...previous, stages: [...previous.stages, stage] } : previous);
      }
    };
    streamActionPlanSuggestions(family, onStage, { signal: current.signal })
      .then((suggestions) => { if (!current.signal.aborted) setState({ status: "ready", suggestions }); })
      .catch((error: unknown) => {
        if (!current.signal.aborted) {
          setState({ status: "error", message: errorMessage(error, "A plan could not be suggested. Try again.") });
        }
      });
  }, [family]);

  useEffect(() => {
    // Started after mount, not during render; a cancel or unmount aborts the request.
    void Promise.resolve().then(load);
    return () => controller.current?.abort();
  }, [load]);

  const cancel = () => {
    controller.current?.abort();
    onClose();
  };

  const suggested = state.status === "ready" ? state.suggestions.plans[0] ?? null : null;
  const entries = suggested ? entriesFor(suggested) : null;
  const allInPlan = Boolean(entries) && [...entries!.steps, ...entries!.alongside].every((id) => plan.saved.has(id));

  const addAll = async () => {
    if (!entries) return;
    setAdding(true);
    const ok = await plan.addSuggested(entries);
    setAdding(false);
    if (ok) onClose();
  };

  return (
    <section aria-labelledby="suggested-plan" className="rounded-2xl border border-border bg-card p-5 shadow-card sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow">Suggested plan</p>
          <h2 id="suggested-plan" className="mt-1 text-section">{suggested ? suggested.title : "A plan for your biggest gaps"}</h2>
          {suggested && <p className="mt-2 max-w-3xl text-muted-foreground">{suggested.summary}</p>}
        </div>
        <Button size="icon-sm" variant="ghost" aria-label="Close suggested plan" onClick={cancel}><X /></Button>
      </div>

      {state.status === "loading" && <PlanBuilding stages={state.stages} onCancel={cancel} />}

      {state.status === "error" && <div className="mt-6 grid justify-items-start gap-3">
        <p role="alert" className="rounded-xl bg-danger-soft px-4 py-3">{state.message}</p>
        <Button variant="outline" onClick={load}><RotateCcw data-icon="inline-start" />Try again</Button>
      </div>}

      {state.status === "ready" && !suggested && <p className="mt-6 rounded-xl bg-sunken px-4 py-3 text-muted-foreground">
        {state.suggestions.uncovered_skill_ids.length
          ? `No resource closes ${names(state.suggestions.uncovered_skill_ids)} yet, so there is nothing to suggest.`
          : "You have no gaps left to plan for. Nice work."}
      </p>}

      {suggested && state.status === "ready" && <>
        <SkillsHighlight plan={suggested} uncovered={state.suggestions.uncovered_skill_ids} gapOrder={gapOrder} />
        {plan.actionError && <p role="alert" className="mt-4 text-sm text-destructive">{plan.actionError}</p>}
        {/* One column: the main path, then what runs alongside it. */}
        <div className="mt-8 grid gap-8">
          <div>
            <p id="suggested-steps" className="eyebrow mb-3">Main path, in order</p>
            <ol aria-labelledby="suggested-steps" className="grid gap-2">
              {suggested.steps.map((item, index) => (
                <SuggestedItem key={item.resource_id} item={item} step={index + 1} order={index} full={index === 0} />
              ))}
            </ol>
          </div>
          {suggested.alongside.length > 0 && <div>
            <p id="suggested-alongside" className="eyebrow mb-3">Alongside</p>
            <ul aria-labelledby="suggested-alongside" className="grid gap-2">
              {suggested.alongside.map((item, index) => (
                <SuggestedItem key={item.resource_id} item={item} order={suggested.steps.length + index} />
              ))}
            </ul>
          </div>}
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-border pt-5">
          <p className="min-w-0 basis-60 text-sm/6 text-muted-foreground">
            {state.suggestions.source === "rules" ? "Built from your gap ranking." : "Add the steps you want, or the whole plan."}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="lg" onClick={onClose} disabled={adding}>Dismiss</Button>
            <Button size="lg" onClick={() => void addAll()} disabled={adding || allInPlan}>
              {adding ? <LoaderCircle data-icon="inline-start" className="motion-safe:animate-spin" />
                : allInPlan ? <Check data-icon="inline-start" /> : <Plus data-icon="inline-start" />}
              {allInPlan ? "All in your plan" : "Add all to my plan"}
            </Button>
          </div>
        </div>
      </>}
    </section>
  );
}

/**
 * The plan's headline: which gaps it closes, in the student's gap order, and how much work it is.
 * Every number is counted from the plan's items or computed by the backend; none comes from the Agent.
 */
function SkillsHighlight({ plan, uncovered, gapOrder }: { plan: ActionPlan; uncovered: string[]; gapOrder: string[] }) {
  const rank = (skill: string) => {
    const index = gapOrder.indexOf(skill);
    return index < 0 ? Number.POSITIVE_INFINITY : index;
  };
  const skills = [...new Set([...plan.covered_skill_ids, ...uncovered])].sort((a, b) => rank(a) - rank(b));
  const onMainPath = (skill: string) => plan.steps.some((item) => item.skill_ids.includes(skill));
  const covered = new Set(plan.covered_skill_ids);
  // All the student's gaps, as the Gaps page counts them; the plan targets only the biggest ones.
  const allGaps = Math.max(gapOrder.length, skills.length);
  const others = allGaps - skills.length;
  const stats = [
    { value: `${covered.size} of ${allGaps}`, label: "gaps covered" },
    { value: plural(plan.steps.length, "step"), label: plan.alongside.length ? `+ ${plan.alongside.length} alongside` : "" },
    ...(plan.project_hours !== null ? [{ value: `≈ ${plan.project_hours} h`, label: "of project work" }] : []),
  ];

  return (
    <div className="entrance-settle mt-6 grid gap-4">
      {/* One line of figures; it wraps between figures, never inside one. */}
      <p className="text-sm/6 text-muted-foreground">
        {stats.map((stat, index) => (
          <span key={stat.value}>
            {index > 0 && " · "}
            <span className="whitespace-nowrap">
              <span className="font-mono font-medium text-foreground">{stat.value}</span>{stat.label && ` ${stat.label}`}
            </span>
          </span>
        ))}
      </p>
      <div>
        <p id="suggested-skills" className="eyebrow mb-2">Skills this plan builds</p>
        <ul aria-labelledby="suggested-skills" className="flex flex-wrap gap-2">
          {skills.map((skill, index) => {
            const isCovered = covered.has(skill);
            const order = rank(skill);
            const detail = !isCovered ? "not covered yet" : onMainPath(skill) ? "" : "alongside";
            return (
              <li key={skill} style={delay(150 + index * 60)}
                className={cn("entrance-pop motion-safe:[animation-delay:var(--delay)] flex min-h-9 max-w-full items-center gap-2 rounded-full py-1 pr-3.5 pl-1 text-sm",
                !isCovered ? "border border-dashed border-line-strong text-muted-foreground"
                  : order === 0 ? "bg-accent text-accent-foreground" : "bg-card")}>
                <span aria-hidden className={cn("grid size-7 shrink-0 place-items-center rounded-full font-mono text-xs",
                  isCovered ? "bg-foreground text-background" : "border border-dashed border-line-strong")}>
                  {Number.isFinite(order) ? order + 1 : "·"}
                </span>
                <span className="min-w-0">
                  <b className={cn(!isCovered && "font-medium")}>{skillLabel(skill)}</b>
                  <span className="text-muted-foreground">{[order === 0 && " · top gap", detail && ` · ${detail}`]}</span>
                </span>
              </li>
            );
          })}
        </ul>
        {others > 0 && <p className="mt-3 text-sm text-muted-foreground">
          This plan focuses on your {plural(skills.length, "biggest gap")}. The other {others} {others === 1 ? "is" : "are"} on
          the <Link href="/gaps" className="font-bold text-foreground underline underline-offset-4">Gaps page</Link>.
        </p>}
      </div>
    </div>
  );
}

/** Numbers ("20 h", "$59/mo …") are monospaced; words ("Self-paced", "Free") stay in the body font. */
const hasNumber = (text: string) => /\d/.test(text);

/**
 * Provider, then time · cost · level, always in that order so cards compare at a glance. A detail a type
 * doesn't have is skipped.
 */
function ResourceDetails({ resource }: { resource: Resource }) {
  const parts = [
    resource.provider && { key: "provider", text: resource.provider, mono: false },
    resource.time && { key: "time", text: resource.time, mono: hasNumber(resource.time) },
    resource.cost && { key: "cost", text: resource.cost, mono: hasNumber(resource.cost) },
    resource.level && { key: "level", text: resource.level, mono: false },
  ].filter((part): part is { key: string; text: string; mono: boolean } => Boolean(part));
  if (!parts.length) return null;
  return (
    <p className="text-sm text-muted-foreground">
      {parts.map((part, index) => (
        <span key={part.key}>{index > 0 && " · "}<span className={cn(part.mono && "font-mono")}>{part.text}</span></span>
      ))}
    </p>
  );
}

/** Delay between cards sliding in when the plan arrives, so it reads as the plan being laid out. */
const REVEAL_STAGGER_MS = 70;

/**
 * One suggested resource. full: the first step, shown as a card with its skills and reason. The rest are
 * one line each; "Why" opens the same skills and reason, so no explanation is lost.
 * step: the step number on the main path; none for alongside items. order: its place in the reveal.
 */
function SuggestedItem({ item, step, order, full = false }: {
  item: ActionPlanItem; step?: number; order: number; full?: boolean;
}) {
  const { resource } = item;
  const [open, setOpen] = useState(false);
  const whyId = useId();
  const title = (
    <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      <span className="font-bold">{step && <span className="sr-only">Step {step}: </span>}{resource.title}</span>
      <Badge>{RESOURCE_TYPES[resource.type].label}</Badge>
    </p>
  );
  const why = <>
    <p className="text-sm">Closes <b>{names(item.skill_ids)}</b></p>
    {item.reason && <p className={cn("mt-2 rounded-lg px-3 py-2 text-sm/6", full ? "bg-accent" : "bg-sunken")}>{item.reason}</p>}
  </>;
  return (
    <li className={cn("entrance-rise motion-safe:[animation-delay:var(--delay)]", step && "grid grid-cols-[1.25rem_minmax(0,1fr)] gap-2 sm:grid-cols-[2rem_minmax(0,1fr)] sm:gap-3")}
      style={delay(order * REVEAL_STAGGER_MS)}>
      {step && <span aria-hidden className={cn("text-right font-mono text-sm text-muted-foreground", full ? "pt-4" : "pt-3.5")}>{step}</span>}
      <div className={cn("rounded-xl bg-card", full ? "p-4" : "px-4 py-2.5",
        step ? "border border-border" : "border border-dashed border-line-strong")}>
        {full ? <>
          <div className="flex items-start gap-3">
            <ResourceIcon type={resource.type} className="size-8 bg-sunken" />
            <div className="min-w-0 flex-1">{title}<ResourceDetails resource={resource} /></div>
          </div>
          <div className="mt-3">{why}</div>
          <div className="mt-3 flex justify-end"><AddButton item={item} /></div>
        </> : <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <div className="min-w-0 flex-1 basis-56">{title}<ResourceDetails resource={resource} /></div>
            {/* Wraps under the title on narrow cards and stays right-aligned, never past the card edge. */}
            <div className="ml-auto flex flex-wrap items-center justify-end gap-1">
              <Button type="button" size="sm" variant="ghost" aria-expanded={open} aria-controls={whyId}
                onClick={() => setOpen((value) => !value)}>
                Why<span className="sr-only">: {resource.title}</span>
                <ChevronDown data-icon="inline-end" className={cn("motion-safe:transition-transform", open && "rotate-180")} />
              </Button>
              <AddButton item={item} />
            </div>
          </div>
          <div id={whyId} hidden={!open} className="mt-2 border-t border-border pt-3 pb-1">{why}</div>
        </>}
      </div>
    </li>
  );
}

/** Add to plan, as a toggle: a card added on its own slots in by gap, like any saved resource. */
function AddButton({ item }: { item: ActionPlanItem }) {
  const plan = usePlan();
  const saved = plan.saved.get(item.resource_id);
  const busy = plan.pending.has(item.resource_id);
  if (saved?.status === "done") {
    return <span className="inline-flex h-9 items-center gap-1.5 text-sm font-bold text-success"><CircleCheck aria-hidden className="size-4" />Done</span>;
  }
  return (
    <Button type="button" size="sm" variant={saved ? "accent" : "secondary"} aria-pressed={Boolean(saved)}
      disabled={busy} onClick={() => void plan.toggleSaved(item.resource_id)}>
      {busy ? <LoaderCircle data-icon="inline-start" className="motion-safe:animate-spin" />
        : saved ? <Check data-icon="inline-start" /> : <Plus data-icon="inline-start" />}
      {saved ? "In your plan" : "Add to plan"}<span className="sr-only">: {item.resource.title}</span>
    </Button>
  );
}
