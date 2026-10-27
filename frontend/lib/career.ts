import type { CoreSkillGapReport, CoreSkillResult, PlanItem, Resource, ResourceType } from "@/types/api";

// Display rules shared by Home, Gaps, Resources, Action plan and Destinations. They read the scores
// the backend saved; nothing here rescores a skill. Kept free of runtime imports for node --test.

export type EvidenceLevel = "strong" | "some" | "listed" | "none";
export type DemandLevel = "high" | "medium" | "low";

/** A listed-only skill scores exactly this (backend scoring_policy.json listed_score). */
const LISTED_SCORE = 0.2;
/** Strong evidence: a gap grade of B+ or better. Below it a skill counts as a gap. */
export const STRONG_STRENGTH = 0.7;

export const EVIDENCE_LABELS: Record<EvidenceLevel, string> = {
  strong: "Strong evidence",
  some: "Some evidence",
  listed: "Listed only",
  none: "Not shown yet",
};

export const DEMAND_LABELS: Record<DemandLevel, string> = {
  high: "High demand",
  medium: "Medium demand",
  low: "Low demand",
};

export function isScored(skill: CoreSkillResult) {
  return skill.resume_evidence_strength !== null && skill.skill_gap !== null && skill.skill_gap_grade !== null;
}

/** Share of postings that require or prefer the skill: the same weight as the gap priority. */
export function demandShare(skill: CoreSkillResult) {
  const { N, required_job_count, preferred_only_job_count } = skill.demand;
  return N > 0 ? (required_job_count + preferred_only_job_count) / N : 0;
}

export function demandLevel(share: number): DemandLevel {
  return share >= 0.3 ? "high" : share >= 0.1 ? "medium" : "low";
}

export function evidenceLevel(strength: number): EvidenceLevel {
  if (strength <= 0) return "none";
  if (strength <= LISTED_SCORE) return "listed";
  return strength < STRONG_STRENGTH ? "some" : "strong";
}

/** Skills employers ask for where the résumé shows less than strong evidence, biggest first. */
export function rankGaps(report: CoreSkillGapReport) {
  return report.skills
    .filter((skill) => isScored(skill) && skill.resume_evidence_strength! < STRONG_STRENGTH && demandShare(skill) > 0)
    .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0) || demandShare(b) - demandShare(a)
      || a.skill_id.localeCompare(b.skill_id));
}

export function rankStrengths(report: CoreSkillGapReport) {
  return report.skills
    .filter((skill) => isScored(skill) && skill.resume_evidence_strength! >= STRONG_STRENGTH)
    .sort((a, b) => b.resume_evidence_strength! - a.resume_evidence_strength! || demandShare(b) - demandShare(a)
      || a.skill_id.localeCompare(b.skill_id));
}

/** Uncertain evidence: no score yet, so neither a gap nor a strength. */
export function needsReview(report: CoreSkillGapReport) {
  return report.skills.filter((skill) => !isScored(skill));
}

export type PlanStep = { resource: Resource; item: PlanItem; skill: string | null };
export type OrderedPlan = {
  done: PlanStep[];
  /** Not done, in order. The first one is the next turn. */
  ahead: PlanStep[];
  /** Ongoing clubs and meetups that run next to the main path. */
  alongside: PlanStep[];
};

/** Courses prepare for certifications, so a certification comes after them for the same gap. */
const TYPE_ORDER: Record<ResourceType, number> = {
  project: 0, online_course: 1, school_course: 2, certification: 3, student_org: 4,
};

/**
 * Order saved resources: done steps first (when they were finished), then the rest by the biggest
 * gap each one closes. gapOrder is rankGaps' skill_ids; skills outside it come last.
 */
export function orderPlan(items: PlanItem[], resources: Resource[], gapOrder: string[]): OrderedPlan {
  const byId = new Map(resources.map((resource) => [resource.id, resource]));
  const rank = (skill: string) => {
    const index = gapOrder.indexOf(skill);
    return index < 0 ? Number.POSITIVE_INFINITY : index;
  };
  const steps: (PlanStep & { rank: number })[] = [];
  for (const item of items) {
    const resource = byId.get(item.resource_id);
    if (!resource) continue;
    const skill = [...resource.skills].sort((a, b) => rank(a) - rank(b))[0] ?? null;
    steps.push({ resource, item, skill, rank: skill === null ? Number.POSITIVE_INFINITY : rank(skill) });
  }
  const strip = ({ resource, item, skill }: PlanStep) => ({ resource, item, skill });
  const done = steps.filter((step) => step.item.status === "done")
    .sort((a, b) => (a.item.done_at ?? "").localeCompare(b.item.done_at ?? ""));
  const open = steps.filter((step) => step.item.status !== "done")
    .sort((a, b) => a.rank - b.rank || TYPE_ORDER[a.resource.type] - TYPE_ORDER[b.resource.type]
      || a.item.saved_at.localeCompare(b.item.saved_at));
  return {
    done: done.map(strip),
    ahead: open.filter((step) => !step.resource.alongside).map(strip),
    alongside: open.filter((step) => step.resource.alongside).map(strip),
  };
}

/** Resources that close a skill, the most direct first (fewest other skills, then by type). */
export function resourcesForSkill(resources: Resource[], skill: string) {
  return resources.filter((resource) => resource.skills.includes(skill))
    .sort((a, b) => a.skills.indexOf(skill) - b.skills.indexOf(skill)
      || TYPE_ORDER[a.type] - TYPE_ORDER[b.type] || a.title.localeCompare(b.title));
}

export const percent = (ratio: number) => `${Math.round(ratio * 100)}%`;
