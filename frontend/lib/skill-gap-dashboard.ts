import type { CoreSkillGapReport, CoreSkillResult } from "@/types/api";

export function hasSkillScore(skill: CoreSkillResult) {
  return skill.resume_evidence_strength !== null && skill.skill_gap !== null && skill.skill_gap_grade !== null;
}

/** Derive counts and the saved priority ordering; never calculate readiness. */
export function summarizeSkillGaps(report: CoreSkillGapReport) {
  const scored = report.skills.filter(hasSkillScore);
  const areas = new Map<string, { id: string; total: number; evidenced: number; absent: number; pending: number }>();
  for (const skill of report.skills) {
    const area = areas.get(skill.module_id) ?? { id: skill.module_id, total: 0, evidenced: 0, absent: 0, pending: 0 };
    area.total++;
    if (!hasSkillScore(skill)) area.pending++;
    else if (skill.resume_evidence_strength === 0) area.absent++;
    else area.evidenced++;
    areas.set(area.id, area);
  }
  return {
    scored: scored.length,
    total: report.core_skill_count,
    pending: report.skills.length - scored.length,
    absent: scored.filter((skill) => skill.resume_evidence_strength === 0).length,
    sampleSize: report.skills[0]?.demand.N ?? null,
    modules: [...areas.values()],
    priorities: scored.filter((skill) => skill.skill_gap! > 0 && skill.priority !== null && skill.priority > 0)
      .sort((a, b) => b.priority! - a.priority!).slice(0, 5),
  };
}
