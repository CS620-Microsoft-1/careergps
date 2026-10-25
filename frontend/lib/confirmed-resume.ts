import type { ResumeAnalysis, ResumeClassification, JobFamily } from "@/types/api";
import type { TargetRole, ExperienceLevel } from "@/lib/options";

const SNAPSHOT_KEY = "careergps.local.confirmed-resume.v1";
const RUNS_KEY = "careergps.local.skill-gap-runs.v1";
const QUEUED_ANALYSIS_KEY = "careergps.local.queued-skill-gap-analysis.v1";

export const ROLE_FAMILIES: Record<TargetRole, JobFamily> = {
  "Software Engineer": "software_engineer",
  "Data Analyst": "data_analyst",
  "AI Engineer": "ai_engineer",
};
export const FAMILY_LABELS: Record<JobFamily, TargetRole> = {
  software_engineer: "Software Engineer",
  data_analyst: "Data Analyst",
  ai_engineer: "AI Engineer",
};

export type ConfirmedResumeSnapshot = {
  version: 1;
  reviewed_resume: ResumeClassification;
  analysis: ResumeAnalysis;
  filename: string;
  job_family: JobFamily;
  confirmed_at: string;
  review_hash: string;
  onboarding: { targetRole: TargetRole; graduationYear: string; location: string; experienceLevel: ExperienceLevel };
};

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${canonical(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export async function resumeHash(resume: ResumeClassification): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(resume));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function saveConfirmedResume(
  analysis: ResumeAnalysis,
  reviewedResume: ResumeClassification,
  onboarding: ConfirmedResumeSnapshot["onboarding"],
): Promise<ConfirmedResumeSnapshot> {
  const snapshot: ConfirmedResumeSnapshot = {
    version: 1,
    reviewed_resume: reviewedResume,
    analysis: { ...analysis, classification: reviewedResume },
    filename: analysis.filename,
    job_family: ROLE_FAMILIES[onboarding.targetRole],
    confirmed_at: new Date().toISOString(),
    review_hash: await resumeHash(reviewedResume),
    onboarding,
  };
  sessionStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshot));
  return snapshot;
}

export function loadConfirmedResume(): ConfirmedResumeSnapshot | null {
  const text = sessionStorage.getItem(SNAPSHOT_KEY);
  if (!text) return null;
  try {
    const value = JSON.parse(text) as ConfirmedResumeSnapshot;
    if (value.version !== 1 || !value.reviewed_resume || !value.analysis || !value.review_hash
        || !Object.hasOwn(FAMILY_LABELS, value.job_family)) return null;
    return value;
  } catch { return null; }
}

export function saveSnapshotFamily(snapshot: ConfirmedResumeSnapshot, family: JobFamily) {
  const next = { ...snapshot, job_family: family,
    onboarding: { ...snapshot.onboarding, targetRole: FAMILY_LABELS[family] } };
  sessionStorage.setItem(SNAPSHOT_KEY, JSON.stringify(next));
  return next;
}

export function clearConfirmedResume() {
  sessionStorage.removeItem(SNAPSHOT_KEY);
  sessionStorage.removeItem(QUEUED_ANALYSIS_KEY);
}

/** Review confirmation authorizes analysis of this exact reviewed selection. */
export function queueSkillGapAnalysis(snapshot: ConfirmedResumeSnapshot) {
  sessionStorage.setItem(QUEUED_ANALYSIS_KEY, JSON.stringify({
    review_hash: snapshot.review_hash,
    job_family: snapshot.job_family,
    confirmed_at: snapshot.confirmed_at,
  }));
}

export function getQueuedSkillGapAnalysis(snapshot: ConfirmedResumeSnapshot): boolean {
  const text = sessionStorage.getItem(QUEUED_ANALYSIS_KEY);
  if (!text) return false;
  try {
    const value: unknown = JSON.parse(text);
    return value !== null && typeof value === "object"
      && "review_hash" in value && value.review_hash === snapshot.review_hash
      && "job_family" in value && value.job_family === snapshot.job_family
      && "confirmed_at" in value && value.confirmed_at === snapshot.confirmed_at;
  } catch { return false; }
}

/** An old request must not consume a more recent Review confirmation. */
export function clearQueuedSkillGapAnalysis(snapshot: ConfirmedResumeSnapshot) {
  if (getQueuedSkillGapAnalysis(snapshot)) sessionStorage.removeItem(QUEUED_ANALYSIS_KEY);
}

function runMap(): Record<string, string> {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(RUNS_KEY) ?? "{}");
    return value !== null && typeof value === "object" && !Array.isArray(value)
      ? value as Record<string, string> : {};
  }
  catch { return {}; }
}

export function getSavedRun(hash: string, family: JobFamily): string | null {
  const value = runMap()[`${hash}:${family}`];
  return typeof value === "string" ? value : null;
}

export function saveRun(hash: string, family: JobFamily, id: string) {
  sessionStorage.setItem(RUNS_KEY, JSON.stringify({ ...runMap(), [`${hash}:${family}`]: id }));
}

/** Remove only the missing run, never a newer analysis saved under the same key. */
export function forgetRun(hash: string, family: JobFamily, id: string) {
  const runs = runMap();
  const key = `${hash}:${family}`;
  if (runs[key] !== id) return;
  delete runs[key];
  sessionStorage.setItem(RUNS_KEY, JSON.stringify(runs));
}
