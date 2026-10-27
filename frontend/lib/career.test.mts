import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { evidenceLevel, orderPlan, rankGaps, rankStrengths, resourcesForSkill } from "./career.ts";

const skill = (skill_id: string, strength: number | null, priority: number | null, required = 10) => ({
  skill_id, skill_name: skill_id, module_id: "m", module_name: "M",
  resume_evidence_strength: strength, skill_gap: strength === null ? null : 1 - strength,
  skill_gap_grade: strength === null ? null : "C", priority, calculation_state: "scored",
  demand: { N: 100, required_ratio: required / 100, preferred_only_ratio: 0, unspecified_ratio: 0,
    required_job_count: required, preferred_only_job_count: 0, unspecified_job_count: 0 },
  agent_assessment: null, local_reference_check: { status: "ok", errors: [] },
});
const report = (skills: ReturnType<typeof skill>[]) => ({
  policy_version: "v12", job_family: "data_analyst" as const, core_skill_count: skills.length, module_count: 1,
  skills, priority_order: [], unscored_skill_ids: [], source_index: {}, database_used: false, limitations: [],
});
const resource = (id: string, type: string, skills: string[], alongside = false) => ({
  id, type: type as "project", title: id, provider: "", meta: "", description: "", skills,
  url: null, school: null, alongside,
});
const item = (resource_id: string, status: "saved" | "done", saved_at: string, done_at: string | null = null) =>
  ({ resource_id, status, saved_at, done_at });

describe("rankGaps", () => {
  it("keeps scored, in-demand skills below strong evidence, biggest priority first", () => {
    const ranked = rankGaps(report([
      skill("sql", 0.2, 0.5), skill("viz", 0, 0.07), skill("python", 0.8, 0.1),
      skill("stats", null, null), skill("rare", 0, 0, 0),
    ]));
    assert.deepEqual(ranked.map((s) => s.skill_id), ["sql", "viz"]);
  });

  it("puts strong evidence in strengths instead", () => {
    assert.deepEqual(rankStrengths(report([skill("python", 0.8, 0.1), skill("sql", 0.2, 0.5)]))
      .map((s) => s.skill_id), ["python"]);
  });
});

describe("evidenceLevel", () => {
  it("separates listed-only skills from practice", () => {
    assert.deepEqual([0, 0.2, 0.45, 0.7].map(evidenceLevel), ["none", "listed", "some", "strong"]);
  });
});

describe("orderPlan", () => {
  const resources = [
    resource("cert", "certification", ["viz"]), resource("course", "online_course", ["viz"]),
    resource("sql-project", "project", ["sql"]), resource("club", "student_org", ["viz"], true),
    resource("done", "project", ["sql"]),
  ];

  it("lists done steps, then the biggest gap first with courses before certifications", () => {
    const plan = orderPlan([
      item("cert", "saved", "2026-10-01"), item("course", "saved", "2026-10-02"),
      item("sql-project", "saved", "2026-10-03"), item("club", "saved", "2026-10-04"),
      item("done", "done", "2026-09-01", "2026-10-05"), item("gone", "saved", "2026-10-06"),
    ], resources, ["viz", "sql"]);
    assert.deepEqual(plan.done.map((s) => s.resource.id), ["done"]);
    assert.deepEqual(plan.ahead.map((s) => s.resource.id), ["course", "cert", "sql-project"]);
    assert.deepEqual(plan.alongside.map((s) => s.resource.id), ["club"]);
    assert.equal(plan.ahead[0].skill, "viz");
  });

  it("finds resources for a skill, most direct first", () => {
    assert.deepEqual(resourcesForSkill(resources, "sql").map((r) => r.id), ["done", "sql-project"]);
  });
});
