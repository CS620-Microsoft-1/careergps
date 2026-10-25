import { apiGet, apiPostJson } from "@/lib/api/client";
import type { JobFamily, ResumeClassification, SkillGapRun } from "@/types/api";

export function startSkillGapRun(input: {
  confirmed: true;
  reviewed_resume: ResumeClassification;
  job_family: JobFamily;
  filename: string;
  confirmed_at: string;
  force?: boolean;
}) {
  return apiPostJson<SkillGapRun>("/skill-gaps/runs", input);
}

export function getSkillGapRun(id: string) {
  return apiGet<SkillGapRun>(`/skill-gaps/runs/${encodeURIComponent(id)}`);
}
