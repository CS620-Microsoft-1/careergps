// Groups résumé skills by how much the résumé itself shows them being used, not by keywords
// alone. Purely local: it only looks at the classified résumé the user confirmed.

import type { ResumeClassification, ResumeRecord } from "@/types/api";

export type EvidenceLevel = "strong" | "some" | "none";

export type SkillEvidence = {
  skill: string;
  level: EvidenceLevel;
  /** Where the skill shows up, e.g. "Data Analyst, Northstar Labs" or "Project: Career Insights". */
  sources: string[];
};

type Source = { label: string; text: string; technologies: string[] };

/**
 * strong: used in a work, research, or leadership entry.
 * some:   used only in projects.
 * none:   listed under skills, with no entry that shows it.
 */
export function rateSkills(classification: ResumeClassification): SkillEvidence[] {
  const roles: Source[] = [
    ...classification.work_experience.map((r) => roleSource(r, "company")),
    ...classification.research_experience.map((r) => roleSource(r, "organization")),
    ...classification.leadership_activities.map((r) => roleSource(r, "organization", "role")),
  ];
  const projects: Source[] = classification.projects.map((r) => ({
    label: `Project: ${text(r.name) || "Untitled"}`,
    text: list(r.content).join("\n"),
    technologies: list(r.technologies),
  }));

  return uniqueSkills(classification).map((skill) => {
    const matches = (source: Source) =>
      source.technologies.some((tech) => sameSkill(tech, skill)) || mentions(source.text, skill);
    const roleHits = roles.filter(matches).map((s) => s.label);
    const projectHits = projects.filter(matches).map((s) => s.label);
    const level: EvidenceLevel = roleHits.length ? "strong" : projectHits.length ? "some" : "none";
    return { skill, level, sources: [...roleHits, ...projectHits] };
  });
}

/** Listed technical skills first, then project technologies not already listed. */
function uniqueSkills(classification: ResumeClassification) {
  const seen = new Set<string>();
  const skills: string[] = [];
  const candidates = [
    ...classification.technical_skills,
    ...classification.projects.flatMap((p) => list(p.technologies)),
  ];
  for (const raw of candidates) {
    const skill = raw.trim();
    const key = skill.toLowerCase();
    if (!skill || seen.has(key)) continue;
    seen.add(key);
    skills.push(skill);
  }
  return skills;
}

function roleSource(record: ResumeRecord, orgKey: string, titleKey = "title"): Source {
  const title = text(record[titleKey]);
  const org = text(record[orgKey]);
  return {
    label: [title, org].filter(Boolean).join(", ") || "Experience entry",
    text: [title, ...list(record.content)].join("\n"),
    technologies: [],
  };
}

function sameSkill(a: string, b: string) {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

/** Whole-word, case-insensitive match that also works for names like "C++", "C#", or "Node.js". */
export function mentions(haystack: string, skill: string) {
  const needle = skill.trim();
  if (!needle || !haystack) return false;
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?<![A-Za-z0-9])${escaped}(?![A-Za-z0-9+#])`, "i").test(haystack);
}

function text(value: ResumeRecord[string]) {
  return typeof value === "string" ? value.trim() : "";
}

function list(value: ResumeRecord[string]) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
}
