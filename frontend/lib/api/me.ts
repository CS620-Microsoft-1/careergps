import { ApiError, apiGet, apiPatch, apiPost, apiPut } from "@/lib/api/client";
import type {
  AccountCreateRequest,
  Destination,
  Goals,
  JobFamily,
  MeResponse,
  PersonalDetails,
  ResumeAddRequest,
  ResumeSummary,
  SavedResume,
  User,
} from "@/types/api";

// backend: app/api/routes/me.py

/** The logged-in student's account; user is null until onboarding is finished. */
export function getMe() {
  return apiGet<MeResponse>("/me");
}

/** Finish onboarding: creates the account and its first résumé. Throws ApiError 409 if already done. */
export function createAccount(body: AccountCreateRequest) {
  return apiPost<MeResponse>("/me", { json: body });
}

/** Change the name, university or career goal; only the fields sent change. */
export function updateAccount(body: Partial<Goals & PersonalDetails>) {
  return apiPatch<User>("/me", { json: body });
}

/** Save a confirmed résumé; the destination for job_family uses it from now on (added if new). */
export function addResume(body: ResumeAddRequest) {
  return apiPost<SavedResume>("/me/resumes", { json: body });
}

/** Add a destination, or change the résumé it uses. Several roles can use the same résumé. */
export function setDestinationResume(jobFamily: JobFamily, resumeId: string) {
  return apiPut<SavedResume>(`/me/destinations/${jobFamily}`, { json: { resume_id: resumeId } });
}

/** The roles the student added, oldest first, with each one's résumé. */
export function listDestinations() {
  return apiGet<Destination[]>("/me/destinations");
}

/** A destination's résumé (the selected target role's by default), or null if it has none. */
export async function getSavedResume(jobFamily?: JobFamily): Promise<SavedResume | null> {
  try {
    return await apiGet<SavedResume>(jobFamily ? `/me/resume?job_family=${jobFamily}` : "/me/resume");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Every confirmed résumé version, newest first, with the roles that use each one. */
export function listResumes() {
  return apiGet<ResumeSummary[]>("/me/resumes");
}
