import type { JobFamily, SavedResume, User } from "@/types/api";

export const FAMILY_LABELS: Record<JobFamily, string> = {
  software_engineer: "Software Engineer",
  data_analyst: "Data Analyst",
  ai_engineer: "AI Engineer",
};

export type SkillGapProfile = {
  user_id: string;
  resume_id: string;
  filename: string;
  confirmed_at: string;
  job_family: JobFamily;
};

export function profileForAnalysis(user: User, resume: SavedResume): SkillGapProfile {
  if (user.active_resume_id !== resume.id) throw new Error("Your active résumé changed. Refresh before analyzing it.");
  const family = (Object.entries(FAMILY_LABELS) as [JobFamily, string][])
    .find(([id, label]) => user.target_role === label || user.target_role === id)?.[0];
  if (!family) throw new Error("Choose a supported target role in your profile before analyzing skill gaps.");
  return { user_id: user.id, resume_id: resume.id, filename: resume.original_filename,
    confirmed_at: resume.created_at, job_family: family };
}

const INTENT_KEY = "careergps.skill-gap-start.v2";
type AnalysisIntent = Pick<SkillGapProfile, "user_id" | "resume_id" | "job_family">;

/** Only identifiers are stored. The confirmed résumé always comes from the API. */
export function queueSkillGapAnalysis(intent: AnalysisIntent) {
  const { user_id, resume_id, job_family } = intent;
  try { sessionStorage.setItem(INTENT_KEY, JSON.stringify({ user_id, resume_id, job_family })); }
  catch { /* The saved profile remains usable; analysis can be started explicitly. */ }
}

/** Consume before any request so failed restores and reloads cannot repeat a paid call. */
export function consumeSkillGapIntent(profile: SkillGapProfile): boolean {
  try {
    const raw = sessionStorage.getItem(INTENT_KEY);
    sessionStorage.removeItem(INTENT_KEY);
    if (!raw) return false;
    const intent: unknown = JSON.parse(raw);
    return Boolean(intent && typeof intent === "object"
      && "user_id" in intent && intent.user_id === profile.user_id
      && "resume_id" in intent && intent.resume_id === profile.resume_id
      && "job_family" in intent && intent.job_family === profile.job_family);
  } catch { return false; }
}
