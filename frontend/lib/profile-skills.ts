import { hasSkillScore } from "@/lib/skill-gap-dashboard";
import type { CoreSkillGapReport, CoreSkillResult } from "@/types/api";

const STRONG_GRADES = new Set(["A", "A-", "B+"]);
const SOME_GRADES = new Set(["B", "C", "D"]);

export type ProfileSkillGroups = {
  strong: CoreSkillResult[];
  some: CoreSkillResult[];
  absent: CoreSkillResult[];
  pending: CoreSkillResult[];
};

function byId(a: CoreSkillResult, b: CoreSkillResult) {
  return a.skill_id < b.skill_id ? -1 : a.skill_id > b.skill_id ? 1 : 0;
}

/** Display existing score bands only; no new score or ability estimate is made. */
export function groupProfileSkills(report: CoreSkillGapReport | null): ProfileSkillGroups {
  const groups: ProfileSkillGroups = { strong: [], some: [], absent: [], pending: [] };
  for (const skill of report?.skills ?? []) {
    const strength = skill.resume_evidence_strength;
    const gap = skill.skill_gap;
    const grade = skill.skill_gap_grade;
    if (!hasSkillScore(skill) || typeof strength !== "number" || !Number.isFinite(strength)
        || strength < 0 || strength > 1 || typeof gap !== "number" || !Number.isFinite(gap)
        || gap < 0 || gap > 1 || typeof grade !== "string") {
      groups.pending.push(skill);
    } else if (strength === 0 && grade === "F" && gap === 1) {
      groups.absent.push(skill);
    } else if (strength > 0 && STRONG_GRADES.has(grade)) {
      groups.strong.push(skill);
    } else if (strength > 0 && SOME_GRADES.has(grade)) {
      groups.some.push(skill);
    } else {
      // Unknown or contradictory classifications must not appear as no evidence.
      groups.pending.push(skill);
    }
  }
  const evidenceOrder = (a: CoreSkillResult, b: CoreSkillResult) =>
    b.resume_evidence_strength! - a.resume_evidence_strength! || byId(a, b);
  groups.strong.sort(evidenceOrder);
  groups.some.sort(evidenceOrder);
  groups.absent.sort((a, b) => (b.priority ?? -Infinity) - (a.priority ?? -Infinity) || byId(a, b));
  groups.pending.sort(byId);
  return groups;
}
