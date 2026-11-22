// Relative import (not "@/"), so node --test can load this file.
import { apiPost } from "./client.ts";
import type { ActionPlanMode, ActionPlanSuggestions, JobFamily } from "@/types/api";

// backend: app/api/routes/action_plans.py

/** A little longer than the backend's 90 s Agent timeout, so an uncached plan can finish. */
export const ACTION_PLAN_TIMEOUT_MS = 100_000;

/** A suggested action plan for the role's latest completed skill gap analysis. */
export function getActionPlanSuggestions(family: JobFamily,
  { mode = "full", signal }: { mode?: ActionPlanMode; signal?: AbortSignal } = {}) {
  return apiPost<ActionPlanSuggestions>("/action-plans/suggestions", {
    json: { job_family: family, mode }, timeoutMs: ACTION_PLAN_TIMEOUT_MS, signal,
  });
}
