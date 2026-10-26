import { apiGet, apiPost } from "@/lib/api/client";
import type { JobFamily, SkillGapRun } from "@/types/api";

export function startSkillGapRun(input: {
  job_family?: JobFamily;
  force?: boolean;
}) {
  return apiPost<SkillGapRun>("/skill-gaps/runs", { json: input });
}

export function getLatestSkillGapRun(family: JobFamily) {
  return apiGet<SkillGapRun>(`/skill-gaps/runs/latest?job_family=${encodeURIComponent(family)}`);
}

export function getSkillGapRun(id: string) {
  return apiGet<SkillGapRun>(`/skill-gaps/runs/${encodeURIComponent(id)}`);
}
