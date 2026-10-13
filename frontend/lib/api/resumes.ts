import { apiPostForm } from "@/lib/api/client";
import type { ResumeAnalysis } from "@/types/api";

const ANALYSIS_TIMEOUT_MS = 180_000;

/** Analyze one résumé without saving the upload, extracted text, or classified JSON. */
export function analyzeResume(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ResumeAnalysis>("/resumes/analyze", form, ANALYSIS_TIMEOUT_MS);
}
