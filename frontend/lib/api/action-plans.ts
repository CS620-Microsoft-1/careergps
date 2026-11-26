// Relative import (not "@/"), so node --test can load this file.
import { ApiError, apiPost, apiPostJsonLines } from "./client.ts";
import type {
  ActionPlanBuildStage, ActionPlanMode, ActionPlanStreamEvent, ActionPlanSuggestions, JobFamily,
} from "@/types/api";

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

/**
 * The same plan, streamed: onStage gets each build stage as it finishes (for the live view), and the
 * promise resolves with the plan. An error line rejects with an ApiError carrying its status and detail.
 */
export async function streamActionPlanSuggestions(family: JobFamily, onStage: (stage: ActionPlanBuildStage) => void,
  { mode = "full", signal }: { mode?: ActionPlanMode; signal?: AbortSignal } = {}): Promise<ActionPlanSuggestions> {
  let result: ActionPlanSuggestions | null = null;
  await apiPostJsonLines<ActionPlanStreamEvent>("/action-plans/suggestions/stream", { job_family: family, mode },
    (event) => {
      if (event.type === "stage") onStage(event);
      else if (event.type === "result") result = event.suggestions;
      else throw new ApiError(event.status, `Action plan stream failed with ${event.status}`, event.detail);
    }, { timeoutMs: ACTION_PLAN_TIMEOUT_MS, signal });
  if (!result) throw new ApiError(0, "The plan stream ended without a result");
  return result;
}
