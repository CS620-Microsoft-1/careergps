import { ApiError, apiPostForm, apiPostFormLines } from "@/lib/api/client";
import type { ResumeAnalysis, ResumeAnalysisEvent, ResumeStepEvent } from "@/types/api";

const ANALYSIS_TIMEOUT_MS = 180_000;

/** Analyze one résumé without saving the upload, extracted text, or classified JSON. */
export function analyzeResume(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ResumeAnalysis>("/resumes/analyze", form, ANALYSIS_TIMEOUT_MS);
}

/**
 * Same analysis, but calls onStep as each backend stage starts and finishes, so the UI can show
 * real progress. Resolves with the result; a failure mid-analysis throws ApiError with the
 * backend's status and detail. Aborting `signal` (Cancel) rejects with the browser's AbortError.
 */
export async function streamResumeAnalysis(
  file: File,
  onStep: (event: ResumeStepEvent) => void,
  signal?: AbortSignal,
): Promise<ResumeAnalysis> {
  const form = new FormData();
  form.append("file", file);
  let result: ResumeAnalysis | undefined;
  await apiPostFormLines<ResumeAnalysisEvent>(
    "/resumes/analyze/stream",
    form,
    (event) => {
      if (event.type === "step") onStep(event);
      else if (event.type === "result") result = event.data;
      else throw new ApiError(event.status, `Résumé analysis failed with ${event.status}`, event.detail);
    },
    { timeoutMs: ANALYSIS_TIMEOUT_MS, signal },
  );
  if (!result) throw new ApiError(0, "The résumé analysis stopped before it finished.");
  return result;
}
