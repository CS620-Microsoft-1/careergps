// One student with a finished Data Analyst analysis, shared by the component and end-to-end tests.
// Typed against the API types, so `npm run typecheck` catches fixtures that drift from the API.

import type {
  CoreSkillGapReport,
  CoreSkillResult,
  Destination,
  MarketDemandSnapshot,
  PlanItem,
  Resource,
  ResumeClassification,
  SavedResume,
  SkillGapRun,
  User,
} from "../types/api";

const POSTINGS = 200;

function skill(skill_id: string, strength: number | null, priority: number | null, required: number): CoreSkillResult {
  return {
    skill_id, skill_name: skill_id, module_id: "databases_data", module_name: "Databases & data",
    resume_evidence_strength: strength, skill_gap: strength === null ? null : 1 - strength,
    skill_gap_grade: strength === null ? null : "C", priority,
    calculation_state: strength === null ? "needs_review" : "scored",
    demand: {
      N: POSTINGS, required_ratio: required / POSTINGS, preferred_only_ratio: 0, unspecified_ratio: 0,
      required_job_count: required, preferred_only_job_count: 0, unspecified_job_count: 0,
    },
    agent_assessment: null, local_reference_check: { status: "ok", errors: [] },
  };
}

/** Two gaps (SQL first), one strength and one skill to review. */
export const report: CoreSkillGapReport = {
  policy_version: "v12", job_family: "data_analyst", core_skill_count: 4, module_count: 1,
  skills: [
    skill("sql", 0.2, 0.5, 140),
    skill("dashboarding", 0.45, 0.2, 60),
    skill("analytical_scripting", 0.85, 0.05, 90),
    skill("statistics", null, null, 50),
  ],
  priority_order: ["sql", "dashboarding"], unscored_skill_ids: ["statistics"], source_index: {},
  database_used: false, limitations: [],
};

export const user: User = {
  id: "user-1", primary_email: "student@example.edu", first_name: "Sam", last_name: "Student",
  full_name: "Sam Student", target_role: "Data Analyst", experience_level: "entry",
  graduation_year: 2027, university: "Example University", preferred_location: "Madison, WI",
  resume_emails: ["student@example.edu"], phones: [], current_location: null,
  linkedin_url: null, github_url: null, website_url: null, created_at: "2026-10-01T00:00:00Z",
};

const classification: ResumeClassification = {
  personal_information: { name: "Sam Student" }, research_interests: [], education: [], work_experience: [],
  research_experience: [], projects: [], technical_skills: ["Python", "Excel"], languages: [], publications: [],
  awards_honors: [], certifications: [], leadership_activities: [], other: [],
};

export const resume: SavedResume = {
  id: "resume-1", original_filename: "sam-resume.pdf", file_type: "pdf", classification,
  created_at: "2026-10-01T00:00:00Z",
};

export const destinations: Destination[] = [
  { job_family: "data_analyst", resume_id: resume.id, original_filename: resume.original_filename,
    created_at: "2026-10-01T00:00:00Z" },
];

export const run: SkillGapRun = {
  id: "run-1", user_id: user.id, resume_id: resume.id, status: "completed", phase: "completed",
  job_family: "data_analyst", filename: resume.original_filename, resume_hash: "hash-1",
  created_at: "2026-10-01T00:00:00Z", completed_at: "2026-10-01T00:01:00Z", elapsed_seconds: 60,
  model_calls: 3, report, error: null, reused: false,
  match: { score: 0.42, scored_skill_count: 3, unscored_skill_count: 1 },
};

export const resources: Resource[] = [
  { id: "sql-course", type: "online_course", title: "SQL for Data Analysis", provider: "Example Courses",
    meta: "6 weeks", description: "Queries, joins and aggregates.", skills: ["sql"],
    url: "https://example.com/sql", school: null, alongside: false },
  { id: "sql-project", type: "project", title: "Analyze a public dataset with SQL", provider: "CareerGPS",
    meta: "2 weekends", description: "", skills: ["sql"], url: null, school: null, alongside: false },
  { id: "dashboard-course", type: "online_course", title: "Building Dashboards", provider: "Example Courses",
    meta: "4 weeks", description: "", skills: ["dashboarding"], url: null, school: null, alongside: false },
  { id: "data-club", type: "student_org", title: "Data Science Club", provider: "Example University",
    meta: "Weekly", description: "", skills: ["dashboarding"], url: null, school: null, alongside: true },
];

export const market: MarketDemandSnapshot = {
  job_family: "data_analyst", sample_size: POSTINGS, core_skill_count: 4, source_analysis_version: "v12",
  snapshot_fingerprint: "fingerprint-1",
  skills: report.skills.map(({ skill_id, module_id, demand }) => ({ skill_id, module_id, ...demand })),
  responsibilities_available: false, common_responsibilities: [], database_used: false,
  snapshot_generated_at: "2026-10-01T00:00:00Z", posting_window: "Sep 2026", company_coverage: 40,
  source_description: "Fixture postings for tests.", coverage_limitations: [],
};

export function planItem(resource_id: string, status: PlanItem["status"] = "saved"): PlanItem {
  return { resource_id, status, saved_at: "2026-10-02T00:00:00Z", done_at: status === "done" ? "2026-10-03T00:00:00Z" : null };
}
