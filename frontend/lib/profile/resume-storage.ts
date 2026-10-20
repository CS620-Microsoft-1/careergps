// Browser-only store for the résumé analysis shown on /profile. The backend keeps none of
// POST /resumes/analyze's output, so onboarding saves the reviewed result here, one key per
// Supabase user id so switching accounts on the same browser never shows someone else's résumé.
// Every read and write is wrapped: private windows, blocked storage, full quota, or a damaged
// value all end up as "nothing saved" instead of an error.

import type { ResumeAnalysis, ResumeClassification } from "@/types/api";

const KEY_PREFIX = "careergps:resume-profile:v1:";
const VERSION = 1;

/** Career goal answers from the onboarding form; the backend has no endpoint that saves them yet. */
export type OnboardingGoals = {
  targetRole: string | null;
  experienceLevel: string | null;
  graduationYear: string | null;
  location: string | null;
};

export type StoredResumeProfile = {
  version: typeof VERSION;
  /** ISO timestamp of when the user confirmed the review. */
  savedAt: string;
  /** The analysis with the classification as the user edited it in the review step. */
  analysis: ResumeAnalysis;
  goals: OnboardingGoals | null;
};

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const STRING_LIST_KEYS = ["research_interests", "technical_skills"] as const;
const RECORD_LIST_KEYS = [
  "education",
  "work_experience",
  "research_experience",
  "projects",
  "languages",
  "publications",
  "awards_honors",
  "certifications",
  "leadership_activities",
  "other",
] as const;

export function resumeProfileKey(userId: string) {
  return `${KEY_PREFIX}${userId}`;
}

/** window.localStorage, or undefined on the server or when the browser blocks access. */
export function browserStorage(): StorageLike | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

/** Saves the confirmed analysis for this user. Returns false if the browser refused it. */
export function saveResumeProfile(
  userId: string,
  analysis: ResumeAnalysis,
  goals: OnboardingGoals | null,
  storage: StorageLike | undefined = browserStorage(),
  now: Date = new Date(),
): boolean {
  if (!storage || !userId) return false;
  const value: StoredResumeProfile = {
    version: VERSION,
    savedAt: now.toISOString(),
    analysis,
    goals,
  };
  try {
    storage.setItem(resumeProfileKey(userId), JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

/** The user's saved analysis, or null when there is none or it can't be read. */
export function loadResumeProfile(
  userId: string,
  storage: StorageLike | undefined = browserStorage(),
): StoredResumeProfile | null {
  if (!storage || !userId) return null;
  try {
    return parseStoredResumeProfile(storage.getItem(resumeProfileKey(userId)));
  } catch {
    return null;
  }
}

export function clearResumeProfile(
  userId: string,
  storage: StorageLike | undefined = browserStorage(),
) {
  if (!storage || !userId) return;
  try {
    storage.removeItem(resumeProfileKey(userId));
  } catch {
    // Nothing else to do; the next save overwrites it anyway.
  }
}

/** Parses and checks a stored value. Anything unexpected returns null (shown as the empty state). */
export function parseStoredResumeProfile(raw: string | null): StoredResumeProfile | null {
  if (!raw) return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isObject(data) || data.version !== VERSION || typeof data.savedAt !== "string") return null;

  const analysis = data.analysis;
  if (!isObject(analysis) || typeof analysis.filename !== "string") return null;
  const classification = parseClassification(analysis.classification);
  if (!classification) return null;

  return {
    version: VERSION,
    savedAt: data.savedAt,
    analysis: { ...(analysis as ResumeAnalysis), classification },
    goals: parseGoals(data.goals),
  };
}

function parseClassification(value: unknown): ResumeClassification | null {
  if (!isObject(value) || !isObject(value.personal_information)) return null;
  for (const key of STRING_LIST_KEYS) {
    const list = value[key];
    if (list !== undefined && !(Array.isArray(list) && list.every((item) => typeof item === "string"))) {
      return null;
    }
  }
  for (const key of RECORD_LIST_KEYS) {
    const list = value[key];
    if (list !== undefined && !(Array.isArray(list) && list.every(isObject))) return null;
  }
  // Fill lists an older or partial result left out, so the page can treat every list as present.
  const filled: Record<string, unknown> = { ...value };
  for (const key of [...STRING_LIST_KEYS, ...RECORD_LIST_KEYS]) filled[key] ??= [];
  return filled as ResumeClassification;
}

function parseGoals(value: unknown): OnboardingGoals | null {
  if (!isObject(value)) return null;
  const text = (field: unknown) => (typeof field === "string" && field.trim() ? field.trim() : null);
  return {
    targetRole: text(value.targetRole),
    experienceLevel: text(value.experienceLevel),
    graduationYear: text(value.graduationYear),
    location: text(value.location),
  };
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
