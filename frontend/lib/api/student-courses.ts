import { apiDelete, apiGet, apiPut } from "@/lib/api/client";
import type { JobFamily, ResumeCourseMatches, TakenCourse, TakenCourseList } from "@/types/api";

// backend: app/api/routes/student_courses.py

export function getTakenCourses() {
  return apiGet<TakenCourseList>("/me/courses");
}

/** source "resume" when the student confirms a match from getResumeCourseMatches. */
export function markCourseTaken(courseId: string, source: "manual" | "resume" = "manual") {
  return apiPut<TakenCourse>(`/me/courses/${encodeURIComponent(courseId)}`, { json: { source } });
}

export function unmarkCourseTaken(courseId: string) {
  return apiDelete(`/me/courses/${encodeURIComponent(courseId)}`);
}

/** Course codes found in the role's résumé. Nothing is saved until the student confirms. */
export function getResumeCourseMatches(family: JobFamily) {
  return apiGet<ResumeCourseMatches>(`/me/courses/resume-matches?job_family=${encodeURIComponent(family)}`);
}
