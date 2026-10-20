import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ResumeAnalysis, ResumeClassification } from "@/types/api";

import {
  clearResumeProfile,
  loadResumeProfile,
  parseStoredResumeProfile,
  resumeProfileKey,
  saveResumeProfile,
} from "./resume-storage.ts";

function memoryStorage() {
  const items = new Map<string, string>();
  return {
    items,
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
    removeItem: (key: string) => void items.delete(key),
  };
}

const throwingStorage = {
  getItem: () => {
    throw new Error("SecurityError");
  },
  setItem: () => {
    throw new Error("QuotaExceededError");
  },
  removeItem: () => {
    throw new Error("SecurityError");
  },
};

const classification: ResumeClassification = {
  personal_information: { name: "Avery Chen", emails: ["avery@example.test"], phones: [] },
  research_interests: [],
  education: [{ institution: "Northlake University", degree: "B.S.", major: "CS", content: [] }],
  work_experience: [],
  research_experience: [],
  projects: [],
  technical_skills: ["Python"],
  languages: [],
  publications: [],
  awards_honors: [],
  certifications: [],
  leadership_activities: [],
  other: [],
};

const analysis: ResumeAnalysis = {
  filename: "resume.pdf",
  extraction: { parser: "pdf", ocr_pages: [], characters: 10, seconds: 0.1, text: "text" },
  agent: { name: "classifier", seconds: 1, validated: true },
  classification,
};

const goals = {
  targetRole: "Data Analyst",
  experienceLevel: "Full-time",
  graduationYear: "2027",
  location: "United States",
};

describe("resume storage", () => {
  it("round-trips a saved analysis for the same user", () => {
    const storage = memoryStorage();
    const now = new Date("2026-10-20T12:00:00Z");
    assert.equal(saveResumeProfile("user-1", analysis, goals, storage, now), true);

    const loaded = loadResumeProfile("user-1", storage);
    assert.ok(loaded);
    assert.equal(loaded.savedAt, "2026-10-20T12:00:00.000Z");
    assert.deepEqual(loaded.analysis, analysis);
    assert.deepEqual(loaded.goals, goals);
  });

  it("keeps each user's data under its own key", () => {
    const storage = memoryStorage();
    saveResumeProfile("user-1", analysis, goals, storage);
    assert.equal(loadResumeProfile("user-2", storage), null);
    assert.ok(storage.items.has(resumeProfileKey("user-1")));
    assert.notEqual(resumeProfileKey("user-1"), resumeProfileKey("user-2"));
  });

  it("returns null when nothing is saved, no storage exists, or no user id is known", () => {
    assert.equal(loadResumeProfile("user-1", memoryStorage()), null);
    assert.equal(loadResumeProfile("user-1", undefined), null);
    assert.equal(loadResumeProfile("", memoryStorage()), null);
    assert.equal(saveResumeProfile("", analysis, goals, memoryStorage()), false);
  });

  it("never throws when the browser blocks storage", () => {
    assert.equal(saveResumeProfile("user-1", analysis, goals, throwingStorage), false);
    assert.equal(loadResumeProfile("user-1", throwingStorage), null);
    assert.doesNotThrow(() => clearResumeProfile("user-1", throwingStorage));
  });

  it("clears only the given user", () => {
    const storage = memoryStorage();
    saveResumeProfile("user-1", analysis, goals, storage);
    saveResumeProfile("user-2", analysis, goals, storage);
    clearResumeProfile("user-1", storage);
    assert.equal(loadResumeProfile("user-1", storage), null);
    assert.ok(loadResumeProfile("user-2", storage));
  });

  it("treats damaged or unexpected values as nothing saved", () => {
    const stored = (value: unknown) => JSON.stringify(value);
    const valid = { version: 1, savedAt: "2026-10-20T00:00:00Z", analysis, goals };
    const cases = [
      "{not json",
      "null",
      "[]",
      stored({ ...valid, version: 2 }),
      stored({ ...valid, savedAt: 5 }),
      stored({ ...valid, analysis: null }),
      stored({ ...valid, analysis: { ...analysis, classification: "x" } }),
      stored({ ...valid, analysis: { ...analysis, classification: { ...classification, personal_information: null } } }),
      stored({ ...valid, analysis: { ...analysis, classification: { ...classification, technical_skills: [1] } } }),
      stored({ ...valid, analysis: { ...analysis, classification: { ...classification, education: ["x"] } } }),
      stored({ ...valid, analysis: { ...analysis, classification: { ...classification, projects: null } } }),
    ];
    for (const raw of cases) assert.equal(parseStoredResumeProfile(raw), null, raw);
  });

  it("fills missing lists and drops malformed goals", () => {
    const partial = { personal_information: {}, technical_skills: ["SQL"] };
    const parsed = parseStoredResumeProfile(
      JSON.stringify({
        version: 1,
        savedAt: "2026-10-20T00:00:00Z",
        analysis: { ...analysis, classification: partial },
        goals: { targetRole: "  ", experienceLevel: 3, graduationYear: "2027" },
      }),
    );
    assert.ok(parsed);
    assert.deepEqual(parsed.analysis.classification.work_experience, []);
    assert.deepEqual(parsed.analysis.classification.technical_skills, ["SQL"]);
    assert.deepEqual(parsed.goals, {
      targetRole: null,
      experienceLevel: null,
      graduationYear: "2027",
      location: null,
    });
  });
});
