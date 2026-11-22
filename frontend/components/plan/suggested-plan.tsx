"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, LoaderCircle, Plus, RotateCcw, Sparkles, X } from "lucide-react";

import { RESOURCE_TYPES, ResourceIcon, skillLabel } from "@/components/career/route-parts";
import { usePlan } from "@/components/plan/plan-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getActionPlanSuggestions } from "@/lib/api/action-plans";
import { errorMessage } from "@/lib/api/client";
import type { ActionPlan, ActionPlanItem, ActionPlanSuggestions, JobFamily } from "@/types/api";

type State =
  | { status: "loading" }
  | { status: "ready"; suggestions: ActionPlanSuggestions }
  | { status: "error"; message: string };

const names = (skillIds: string[]) => skillIds.map(skillLabel).join(", ");

/**
 * An optional suggested plan on the Action plan page. It asks the backend once when it opens; nothing in
 * the saved plan changes until the student clicks "Add all to my plan".
 */
export function SuggestedPlan({ family, onClose }: { family: JobFamily; onClose: () => void }) {
  const plan = usePlan();
  const [state, setState] = useState<State>({ status: "loading" });
  const [adding, setAdding] = useState(false);
  const controller = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setState({ status: "loading" });
    getActionPlanSuggestions(family, { signal: current.signal })
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

  const addAll = async (suggestion: ActionPlan) => {
    setAdding(true);
    const ok = await plan.addPlan(suggestion.steps.map((item) => item.resource_id),
      suggestion.alongside.map((item) => item.resource_id));
    setAdding(false);
    if (ok) onClose();
  };

  return (
    <section aria-labelledby="suggested-plan" className="rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow flex items-center gap-2"><Sparkles aria-hidden className="size-4" />Suggested plan</p>
          <h2 id="suggested-plan" className="mt-1 text-section">{suggested ? suggested.title : "A plan for your biggest gaps"}</h2>
          {suggested && <p className="mt-2 max-w-3xl text-muted-foreground">{suggested.summary}</p>}
        </div>
        <Button size="icon-sm" variant="ghost" aria-label="Close suggested plan" onClick={cancel}><X /></Button>
      </div>

      {state.status === "loading" && <div className="mt-6 flex flex-wrap items-center gap-3">
        <p role="status" className="flex items-center gap-2 text-muted-foreground">
          <LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />Building your plan… this can take up to a minute.
        </p>
        <Button variant="ghost" size="sm" onClick={cancel}>Cancel</Button>
      </div>}

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
        {plan.actionError && <p role="alert" className="mt-4 text-sm text-destructive">{plan.actionError}</p>}
        <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.6fr)]">
          <div>
            <p className="eyebrow mb-3">Main path, in order</p>
            <ol className="grid gap-3">
              {suggested.steps.map((item, index) => <SuggestedItem key={item.resource_id} item={item} label={String(index + 1)} />)}
            </ol>
          </div>
          {suggested.alongside.length > 0 && <div>
            <p className="eyebrow mb-3">Alongside</p>
            <ul className="grid gap-3">
              {suggested.alongside.map((item) => <SuggestedItem key={item.resource_id} item={item} />)}
            </ul>
          </div>}
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-border pt-5">
          <p className="min-w-0 basis-80 text-sm/6 text-muted-foreground">
            {[
              suggested.covered_skill_ids.length ? `Covers ${names(suggested.covered_skill_ids)}.` : "",
              suggested.project_hours !== null ? `About ${suggested.project_hours} hours of project work.` : "",
              state.suggestions.uncovered_skill_ids.length
                ? `No resource closes ${names(state.suggestions.uncovered_skill_ids)} yet.` : "",
              state.suggestions.source === "rules" ? "Built from your gap ranking." : "",
            ].filter(Boolean).join(" ")}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="lg" onClick={onClose} disabled={adding}>Dismiss</Button>
            <Button size="lg" onClick={() => void addAll(suggested)} disabled={adding}>
              {adding ? <LoaderCircle data-icon="inline-start" className="motion-safe:animate-spin" /> : <Plus data-icon="inline-start" />}
              Add all to my plan
            </Button>
          </div>
        </div>
      </>}
    </section>
  );
}

/** label: the step number on the main path; none for alongside items. */
function SuggestedItem({ item, label }: { item: ActionPlanItem; label?: string }) {
  const plan = usePlan();
  const { resource } = item;
  const inPlan = plan.saved.has(item.resource_id);
  return (
    <li className={label ? "grid grid-cols-[2rem_minmax(0,1fr)] gap-3" : undefined}>
      {label && <span aria-hidden className="pt-4 text-right font-mono text-sm text-muted-foreground">{label}</span>}
      <div className={label ? "rounded-xl border border-border bg-card p-4" : "rounded-xl border border-dashed border-line-strong bg-card p-4"}>
        <div className="flex items-start gap-3">
          <ResourceIcon type={resource.type} className="size-8 bg-sunken" />
          <div className="min-w-0 flex-1">
            <p className="font-bold">{label && <span className="sr-only">Step {label}: </span>}{resource.title}</p>
            <p className="text-sm text-muted-foreground">
              {[RESOURCE_TYPES[resource.type].label, resource.provider, resource.meta].filter(Boolean).join(" · ")}
            </p>
          </div>
          {inPlan && <Badge variant="success" className="shrink-0"><Check aria-hidden className="size-3.5" />In your plan</Badge>}
        </div>
        <p className="mt-3 text-sm">Closes <b>{names(item.skill_ids)}</b></p>
        <p className="mt-2 rounded-lg bg-accent px-3 py-2 text-sm/6">{item.reason}</p>
      </div>
    </li>
  );
}
