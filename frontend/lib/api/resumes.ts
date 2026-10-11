import { apiGet, apiPost } from "@/lib/api/client";
import type { Resume, ResumeData, ResumeSummary } from "@/types/api";

// backend: app/api/routes/resumes.py

const UPLOAD_TIMEOUT_MS = 60_000; // up to 10 MB on a slow connection

/**
 * Upload a PDF; parsing starts in the background. Throws ApiError 409 if the user already has a
 * résumé that didn't fail, 413/415/422 for a file the API rejects (detail says why).
 */
export function uploadResume(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiPost<ResumeSummary>("/resumes", { form, timeoutMs: UPLOAD_TIMEOUT_MS });
}

export function getResume(id: string) {
  return apiGet<Resume>(`/resumes/${id}`);
}

/** Parse a failed résumé again. */
export function retryResume(id: string) {
  return apiPost<ResumeSummary>(`/resumes/${id}/retry`);
}

/** Save the user-checked data. Only allowed while the résumé is "parsed". */
export function confirmResume(id: string, data: ResumeData) {
  return apiPost<Resume>(`/resumes/${id}/confirm`, { json: data });
}
