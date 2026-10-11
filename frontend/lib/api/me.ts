import { apiGet, apiPatch, apiPost } from "@/lib/api/client";
import type { AccountCreateRequest, MeResponse, Profile } from "@/types/api";

// backend: app/api/routes/me.py

/** The logged-in user's account, profile and résumé summary. */
export function getMe() {
  return apiGet<MeResponse>("/me");
}

/** Finish sign-up after email confirmation. Throws ApiError 409 if already done. */
export function createAccount(body: AccountCreateRequest) {
  return apiPost<MeResponse>("/me", { json: body });
}

export function updateProfile(body: { location: string }) {
  return apiPatch<Profile>("/me/profile", { json: body });
}
