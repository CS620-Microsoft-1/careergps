import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api/client";
import type {
  CertificationRecommendations, JobFamily, Plan, PlanItem, PlanStatus, ProjectRecommendations, ResourceList,
} from "@/types/api";

// backend: app/api/routes/resources.py

/** A little longer than the backend's project agent timeout (120 s), so an uncached pick can finish. */
const PROJECT_PICKS_TIMEOUT_MS = 130_000;

/** Resources that close the role's skills; school-specific ones follow the account's university. */
export function getResources(family: JobFamily) {
  return apiGet<ResourceList>(`/resources?job_family=${encodeURIComponent(family)}`);
}

export function getPlan(family: JobFamily) {
  return apiGet<Plan>(`/plan?job_family=${encodeURIComponent(family)}`);
}

/** Save a resource to the plan ("saved"), or mark it done or not done. Its position, if any, is kept. */
export function setPlanItem(family: JobFamily, resourceId: string, status: PlanStatus) {
  return apiPut<PlanItem>(`/plan/items/${encodeURIComponent(resourceId)}`, { json: { job_family: family, status } });
}

/**
 * Add a whole suggested action plan in one request: steps get positions 1..N in order, alongside items
 * none, and every other saved item loses its position. Returns the whole plan.
 */
export function saveSuggestedPlan(family: JobFamily, steps: string[], alongside: string[]) {
  return apiPut<Plan>("/plan/suggested", { json: { job_family: family, steps, alongside } });
}

export function removePlanItem(family: JobFamily, resourceId: string) {
  return apiDelete(`/plan/items/${encodeURIComponent(resourceId)}?job_family=${encodeURIComponent(family)}`);
}

/** Certifications picked for a role's latest analysis (backend: app/api/routes/certifications.py). */
export function getCertificationPicks(family: JobFamily) {
  return apiPost<CertificationRecommendations>("/certifications/recommendations", { json: { job_family: family } });
}

/** Projects picked for one completed analysis. */
export function getProjectPicks(runId: string) {
  return apiPost<ProjectRecommendations>("/resources/projects/from-skill-gap", {
    json: { run_id: runId }, timeoutMs: PROJECT_PICKS_TIMEOUT_MS,
  });
}
