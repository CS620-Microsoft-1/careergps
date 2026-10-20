import { ApiError, apiGet, apiPatch, apiPost, apiPut } from "@/lib/api/client";
import type {
  AccountCreateRequest,
  MeResponse,
  Profile,
  ProfileUpdateRequest,
  ResumeClassification,
  SavedResume,
} from "@/types/api";

// backend: app/api/routes/me.py

/** The logged-in user's account and profile. */
export function getMe() {
  return apiGet<MeResponse>("/me");
}

/** Finish sign-up after email confirmation. Throws ApiError 409 if already done. */
export function createAccount(body: AccountCreateRequest) {
  return apiPost<MeResponse>("/me", { json: body });
}

export function updateProfile(body: ProfileUpdateRequest) {
  return apiPatch<Profile>("/me/profile", { json: body });
}

/** The résumé analysis saved in onboarding, or null if there is none yet. */
export async function getSavedResume(): Promise<SavedResume | null> {
  try {
    return await apiGet<SavedResume>("/me/resume");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Save the reviewed classification, replacing any earlier one. */
export function saveResume(body: { filename: string; classification: ResumeClassification }) {
  return apiPut<SavedResume>("/me/resume", { json: body });
}
