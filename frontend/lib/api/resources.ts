import { apiDelete, apiGet, apiPut } from "@/lib/api/client";
import type { JobFamily, Plan, PlanItem, PlanStatus, ResourceList } from "@/types/api";

// backend: app/api/routes/resources.py

/** Resources that close the role's skills; school-specific ones follow the account's university. */
export function getResources(family: JobFamily) {
  return apiGet<ResourceList>(`/resources?job_family=${encodeURIComponent(family)}`);
}

export function getPlan(family: JobFamily) {
  return apiGet<Plan>(`/plan?job_family=${encodeURIComponent(family)}`);
}

/** Save a resource to the plan ("saved"), or mark it done or not done. */
export function setPlanItem(family: JobFamily, resourceId: string, status: PlanStatus) {
  return apiPut<PlanItem>(`/plan/items/${encodeURIComponent(resourceId)}`, { json: { job_family: family, status } });
}

export function removePlanItem(family: JobFamily, resourceId: string) {
  return apiDelete(`/plan/items/${encodeURIComponent(resourceId)}?job_family=${encodeURIComponent(family)}`);
}
