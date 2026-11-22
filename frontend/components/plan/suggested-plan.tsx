"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, CircleCheck, LoaderCircle, Plus, RotateCcw, Sparkles, X } from "lucide-react";

import { RESOURCE_TYPES, ResourceIcon, skillLabel } from "@/components/career/route-parts";
import { type PlanEntry, usePlan } from "@/components/plan/plan-provider";
import { Button } from "@/components/ui/button";
import { PlanBuilding } from "@/components/plan/plan-building";
import { streamActionPlanSuggestions } from "@/lib/api/action-plans";
import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import type { ActionPlan, ActionPlanBuildStage, ActionPlanItem, ActionPlanSuggestions, JobFamily } from "@/types/api";

type State =
  | { status: "loading"; stages: ActionPlanBuildStage[] }
  | { status: "ready"; suggestions: ActionPlanSuggestions }
  | { status: "error"; message: string };

const names = (skillIds: string[]) => skillIds.map(skillLabel).join(", ");
/** A stagger delay, applied only when motion is allowed (see the motion-safe:[animation-delay] classes). */
const delay = (ms: number) => ({ "--delay": `${ms}ms` }) as React.CSSProperties;
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** Main-path steps keep their step number as position, so adding them one by one keeps the order. */
const entriesFor = (plan: ActionPlan): PlanEntry[] => [
  ...plan.steps.map((item, index) => ({ resourceId: item.resource_id, position: index + 1 })),
  ...plan.alongside.map((item) => ({ resourceId: item.resource_id })),
];

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
  const entries = suggested ? entriesFor(suggested) : [];
  const allInPlan = entries.length > 0 && entries.every((entry) => plan.saved.has(entry.resourceId));

  const addAll = async () => {
    setAdding(true);
    const ok = await plan.addItems(entries);
    setAdding(false);
    if (ok) onClose();
  };

  return (
    <section aria-labelledby="suggested-plan" className="rounded-2xl border border-border bg-card p-5 shadow-card sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow flex items-center gap-2"><Sparkles aria-hidden className="size-4" />Suggested plan</p>
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
        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.6fr)]">
          <div>
            <p id="suggested-steps" className="eyebrow mb-3">Main path, in order</p>
            <ol aria-labelledby="suggested-steps" className="grid gap-3">
              {suggested.steps.map((item, index) => <SuggestedItem key={item.resource_id} item={item} step={index + 1} order={index} />)}
            </ol>
          </div>
          {suggested.alongside.length > 0 && <div>
            <p id="suggested-alongside" className="eyebrow mb-3">Alongside</p>
            <ul aria-labelledby="suggested-alongside" className="grid gap-3">
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
  const stepsFor = (skill: string) => plan.steps.filter((item) => item.skill_ids.includes(skill)).length;
  const covered = new Set(plan.covered_skill_ids);
  const tiles = [
    { value: `${covered.size} of ${skills.length}`, label: "gaps covered" },
    { value: plural(plan.steps.length, "step"), label: plan.alongside.length ? `+ ${plan.alongside.length} alongside` : "on the main path" },
    ...(plan.project_hours !== null ? [{ value: `≈ ${plan.project_hours} h`, label: "of project work" }] : []),
  ];

  return (
    <div className="entrance-settle mt-6 grid gap-5 rounded-xl bg-sunken p-4 sm:p-5">
      {/* Phones: one compact row per figure. From sm: tiles side by side. */}
      <dl className="grid gap-2 sm:grid-flow-col sm:auto-cols-fr sm:gap-3">
        {tiles.map((tile) => (
          // Label after the value on screen, before it in the markup (dt then dd).
          <div key={tile.label} className="flex min-w-0 flex-row-reverse items-baseline justify-end gap-2 rounded-lg bg-card px-3 py-2 sm:flex-col-reverse sm:items-start sm:gap-0 sm:px-4 sm:py-3">
            <dt className="text-sm text-muted-foreground">{tile.label}</dt>
            <dd className="font-mono text-base font-medium whitespace-nowrap sm:text-xl">{tile.value}</dd>
          </div>
        ))}
      </dl>
      <div>
        <p id="suggested-skills" className="eyebrow mb-2">Skills this plan builds</p>
        <ul aria-labelledby="suggested-skills" className="flex flex-wrap gap-2">
          {skills.map((skill, index) => {
            const isCovered = covered.has(skill);
            const steps = stepsFor(skill);
            const order = rank(skill);
            const detail = !isCovered ? "not covered yet" : steps ? plural(steps, "step") : "alongside";
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
                  <span className="text-muted-foreground">{order === 0 ? " · top gap" : ""} · {detail}</span>
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

/** Delay between cards sliding in when the plan arrives, so it reads as the plan being laid out. */
const REVEAL_STAGGER_MS = 70;

/** step: the step number on the main path; none for alongside items. order: its place in the reveal. */
function SuggestedItem({ item, step, order }: { item: ActionPlanItem; step?: number; order: number }) {
  const plan = usePlan();
  const { resource } = item;
  const saved = plan.saved.get(item.resource_id);
  const busy = plan.pending.has(item.resource_id);
  const toggle = () => void (saved ? plan.remove(item.resource_id)
    : plan.addItems([{ resourceId: item.resource_id, position: step }]));
  return (
    <li className={cn("entrance-rise motion-safe:[animation-delay:var(--delay)]", step && "grid grid-cols-[1.25rem_minmax(0,1fr)] gap-2 sm:grid-cols-[2rem_minmax(0,1fr)] sm:gap-3")}
      style={delay(order * REVEAL_STAGGER_MS)}>
      {step && <span aria-hidden className="pt-4 text-right font-mono text-sm text-muted-foreground">{step}</span>}
      <div className={cn("rounded-xl bg-card p-4", step ? "border border-border" : "border border-dashed border-line-strong")}>
        <div className="flex items-start gap-3">
          <ResourceIcon type={resource.type} className="size-8 bg-sunken" />
          <div className="min-w-0 flex-1">
            <p className="font-bold">{step && <span className="sr-only">Step {step}: </span>}{resource.title}</p>
            <p className="text-sm text-muted-foreground">
              {[RESOURCE_TYPES[resource.type].label, resource.provider, resource.meta].filter(Boolean).join(" · ")}
            </p>
          </div>
        </div>
        <p className="mt-3 text-sm">Closes <b>{names(item.skill_ids)}</b></p>
        <p className="mt-2 rounded-lg bg-accent px-3 py-2 text-sm/6">{item.reason}</p>
        <div className="mt-3 flex justify-end">
          {saved?.status === "done"
            ? <span className="inline-flex h-9 items-center gap-1.5 text-sm font-bold text-success"><CircleCheck aria-hidden className="size-4" />Done</span>
            : <Button type="button" size="sm" variant={saved ? "accent" : "secondary"} aria-pressed={Boolean(saved)}
              disabled={busy} onClick={toggle}>
              {busy ? <LoaderCircle data-icon="inline-start" className="motion-safe:animate-spin" />
                : saved ? <Check data-icon="inline-start" /> : <Plus data-icon="inline-start" />}
              {saved ? "In your plan" : "Add to plan"}<span className="sr-only">: {resource.title}</span>
            </Button>}
        </div>
      </div>
    </li>
  );
}
