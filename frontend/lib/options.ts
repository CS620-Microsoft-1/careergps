// Fixed choices offered in the sign-up and onboarding forms.

export const TARGET_ROLES = [
  "Software Engineer",
  "Data Analyst",
  "AI Engineer",
] as const;
export type TargetRole = (typeof TARGET_ROLES)[number];

export const EXPERIENCE_LEVELS = ["Internship", "Full-time"] as const;
export type ExperienceLevel = (typeof EXPERIENCE_LEVELS)[number];

export const DEFAULT_UNIVERSITY = "University of Wisconsin–Madison";


export const RESUME_ACCEPT = ".pdf,.docx";
export const RESUME_MIME_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];
export const RESUME_MAX_BYTES = 10 * 1024 * 1024;
