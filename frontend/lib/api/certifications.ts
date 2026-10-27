import { apiGet, apiPost } from "@/lib/api/client";
import type { CertificationCatalog, CertificationRecommendations, JobFamily } from "@/types/api";

export function getCertificationCatalog(family: JobFamily) {
  return apiGet<CertificationCatalog>(`/certifications/catalog/${encodeURIComponent(family)}`);
}

/** The first call for a skill gap run asks the Agent, so allow well beyond the 5 s default. */
export function getCertificationRecommendations(family: JobFamily) {
  return apiPost<CertificationRecommendations>("/certifications/recommendations", {
    json: { job_family: family },
    timeoutMs: 120_000,
  });
}
