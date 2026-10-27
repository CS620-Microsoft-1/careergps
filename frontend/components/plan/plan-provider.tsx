"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { errorMessage } from "@/lib/api/client";
import { getPlan, getResources, removePlanItem, setPlanItem } from "@/lib/api/resources";
import type { JobFamily, PlanItem, PlanStatus, Resource } from "@/types/api";

type PlanState = {
  family: JobFamily | null;
  status: "idle" | "loading" | "ready" | "error";
  resources: Resource[];
  items: PlanItem[];
  error?: string;
};
type PlanContextValue = PlanState & {
  /** resource_id → its saved item, for quick lookups in cards. */
  saved: Map<string, PlanItem>;
  /** Resource ids with a save or removal in flight. */
  pending: Set<string>;
  setStatus: (resourceId: string, status: PlanStatus) => Promise<void>;
  remove: (resourceId: string) => Promise<void>;
  toggleSaved: (resourceId: string) => Promise<void>;
  actionError?: string;
};

const PlanContext = createContext<PlanContextValue | null>(null);

/** Resources and saved plan items for the selected role, shared by every page that shows them. */
export function PlanProvider({ children }: { children: React.ReactNode }) {
  const { snapshot, family } = useSkillGapAnalysis();
  const activeFamily = snapshot ? family : null;
  const [state, setState] = useState<PlanState>({ family: null, status: "idle", resources: [], items: [] });
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [actionError, setActionError] = useState<string>();

  useEffect(() => {
    if (!activeFamily) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setState({ family: activeFamily, status: "loading", resources: [], items: [] });
      try {
        const [resources, plan] = await Promise.all([getResources(activeFamily), getPlan(activeFamily)]);
        if (active) setState({ family: activeFamily, status: "ready", resources: resources.resources, items: plan.items });
      } catch (error) {
        if (active) setState({ family: activeFamily, status: "error", resources: [], items: [],
          error: errorMessage(error, "Resources could not be loaded.") });
      }
    });
    return () => { active = false; };
  }, [activeFamily]);

  const track = useCallback(async (resourceId: string, work: () => Promise<void>) => {
    setPending((current) => new Set(current).add(resourceId));
    setActionError(undefined);
    try {
      await work();
    } catch (error) {
      setActionError(errorMessage(error, "Your plan could not be updated. Try again."));
    } finally {
      setPending((current) => {
        const next = new Set(current);
        next.delete(resourceId);
        return next;
      });
    }
  }, []);

  const setStatus = useCallback((resourceId: string, status: PlanStatus) => track(resourceId, async () => {
    if (!state.family) return;
    const item = await setPlanItem(state.family, resourceId, status);
    setState((current) => current.family !== state.family ? current
      : { ...current, items: [...current.items.filter((i) => i.resource_id !== resourceId), item] });
  }), [state.family, track]);

  const remove = useCallback((resourceId: string) => track(resourceId, async () => {
    if (!state.family) return;
    await removePlanItem(state.family, resourceId);
    setState((current) => current.family !== state.family ? current
      : { ...current, items: current.items.filter((i) => i.resource_id !== resourceId) });
  }), [state.family, track]);

  const saved = useMemo(() => new Map(state.items.map((item) => [item.resource_id, item])), [state.items]);
  const toggleSaved = useCallback(
    (resourceId: string) => saved.has(resourceId) ? remove(resourceId) : setStatus(resourceId, "saved"),
    [remove, saved, setStatus],
  );

  const current = state.family === activeFamily ? state
    : { family: activeFamily, status: activeFamily ? "loading" as const : "idle" as const, resources: [], items: [] };
  return (
    <PlanContext value={{ ...current, saved: current === state ? saved : new Map(), pending, setStatus, remove,
      toggleSaved, actionError }}>
      {children}
    </PlanContext>
  );
}

export function usePlan() {
  const value = useContext(PlanContext);
  if (!value) throw new Error("usePlan must be inside PlanProvider");
  return value;
}
