import { ApiError, apiGet, apiPatch, apiPost } from "@/lib/api/client";
import type {
  AccountCreateRequest,
  Goals,
  MeResponse,
  ResumeSubmitRequest,
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

/** Change the career goal; only the fields sent change. */
export function updateGoals(body: Partial<Goals>) {
  return apiPatch<User>("/me", { json: body });
}

/** Save a newer confirmed résumé; it becomes the active one. */
export function addResume(body: ResumeSubmitRequest) {
  return apiPost<SavedResume>("/me/resumes", { json: body });
}

/** The active résumé, or null if there is none yet. */
export async function getSavedResume(): Promise<SavedResume | null> {
  try {
    return await apiGet<SavedResume>("/me/resume");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
