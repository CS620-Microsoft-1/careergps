import { test as base, expect, type Page, type Route } from "@playwright/test";

import type {
  CertificationRecommendations, Plan, ProjectRecommendations, Resource, ResourceList, SavedResume, SkillGapRun,
  TakenCourse, TakenCourseList, User,
} from "../types/api";
import { API_PREFIX } from "../playwright.config";

/**
 * The backend, answered from fixed data for one data-analyst student at UW–Madison.
 *
 * Only `taken` changes during a test (PUT/DELETE /me/courses). Every call is recorded in `calls` as
 * "METHOD /path" when it arrives, so a test can check what the page sent. A test can set
 * `resumeMatches` before the page loads.
 */
export class MockApi {
  readonly taken = new Set<string>();
  readonly calls: string[] = [];
  /** Course ids GET /me/courses/resume-matches answers with. */
  resumeMatches: string[] = [];
  private held: Promise<void> = Promise.resolve();

  /** Keep PUT /me/courses/{id} unanswered until the returned function is called. */
  holdSaves(): () => void {
    let release = () => {};
    this.held = new Promise<void>((resolve) => { release = resolve; });
    return release;
  }

  constructor(private readonly page: Page) {}

  async install() {
    await this.page.route(`**${API_PREFIX}/**`, (route) => this.handle(route));
  }

  private handle(route: Route) {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname.slice(API_PREFIX.length);
    this.calls.push(`${method} ${path}`);
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (method === "GET") {
      switch (path) {
        // The status badge only needs a 2xx here.
        case "/health/db": return json(200, { status: "ok", database: "ok" });
        case "/me": return json(200, { user: USER });
        case "/me/resume": return json(200, RESUME);
        case "/skill-gaps/runs/latest": return json(200, RUN);
        case `/skill-gaps/runs/${RUN.id}`: return json(200, RUN);
        case "/resources": return json(200, { job_family: FAMILY, resources: RESOURCES } satisfies ResourceList);
        case "/plan": return json(200, { job_family: FAMILY, items: [] } satisfies Plan);
        case "/me/courses": return json(200, { courses: [...this.taken].map(takenCourse) } satisfies TakenCourseList);
        case "/me/courses/resume-matches": return json(200, { course_ids: this.resumeMatches });
      }
    }
    const course = path.match(/^\/me\/courses\/([^/]+)$/)?.[1];
    if (course && method === "PUT") {
      return this.held.then(() => {
        this.taken.add(course);
        return json(200, takenCourse(course));
      });
    }
    if (course && method === "DELETE") {
      this.taken.delete(course);
      return route.fulfill({ status: 204 });
    }
    if (method === "POST" && path === "/certifications/recommendations") {
      const picks: CertificationRecommendations = { job_family: FAMILY, skill_gap_run_id: RUN.id, source: "rules",
        generated_at: NOW, recommendations: [] };
      return json(200, picks);
    }
    if (method === "POST" && path === "/resources/projects/from-skill-gap") {
      const picks: ProjectRecommendations = { source: "rules", recommendations: [], no_match_reason: "Not part of this test." };
      return json(200, picks);
    }
    return json(404, { detail: `No mock for ${method} ${path}` });
  }
}

/**
 * Each test gets its own mock, installed before the first page load. `auto` installs it even for a
 * test that doesn't name `api`; otherwise the page would hit the dev server and get 404s.
 */
export const test = base.extend<{ api: MockApi }>({
  // Named `provide`, not Playwright's usual `use`, so the React hooks lint rule leaves it alone.
  api: [async ({ page }, provide) => {
    const api = new MockApi(page);
    await api.install();
    await provide(api);
  }, { auto: true }],
});
export { expect };

// ── Fixed data ──────────────────────────────────────────────────────────────────────────────────

const FAMILY = "data_analyst" as const;
const NOW = "2026-11-09T12:00:00+00:00";
const SCHOOL = "University of Wisconsin–Madison";

const USER: User = {
  id: "11111111-1111-4111-8111-111111111111", primary_email: "avery@example.com",
  first_name: "Avery", last_name: "Chen", full_name: "Avery Chen", target_role: "Data Analyst",
  experience_level: "Internship", graduation_year: 2027, university: SCHOOL, preferred_location: "Madison, WI",
  resume_emails: [], phones: [], current_location: null, linkedin_url: null, github_url: null, website_url: null,
  created_at: NOW,
};

// The pages under test only read id, original_filename and created_at.
const RESUME = {
  id: "22222222-2222-4222-8222-222222222222", original_filename: "avery.pdf", file_type: "pdf",
  classification: { personal_information: {} }, created_at: NOW,
} as unknown as SavedResume;

/** A completed analysis with three data-analyst gaps; Data modeling ranks first. */
function skill(skill_id: string, skill_name: string, strength: number, required: number) {
  const gap = Math.round((1 - strength) * 1000) / 1000;
  return {
    skill_id, skill_name, module_id: "data_foundations", module_name: "Data foundations",
    resume_evidence_strength: strength, skill_gap: gap, skill_gap_grade: "C", priority: gap * required / 100,
    calculation_state: "scored",
    demand: { N: 100, required_ratio: required / 100, preferred_only_ratio: 0, unspecified_ratio: 1 - required / 100,
      required_job_count: required, preferred_only_job_count: 0, unspecified_job_count: 100 - required },
    agent_assessment: null, local_reference_check: { status: "ok", errors: [] },
  };
}
const SKILLS = [
  skill("data_modeling", "Data modeling", 0, 40),
  skill("analytical_scripting", "Analytical scripting", 0.2, 46),
  skill("statistics", "Statistics", 0.45, 18),
];
const RUN = {
  id: "0123456789abcdef0123456789abcdef", user_id: USER.id, resume_id: RESUME.id, status: "completed",
  phase: "completed", job_family: FAMILY, filename: RESUME.original_filename, resume_hash: "e2e", created_at: NOW,
  completed_at: NOW, elapsed_seconds: 1, model_calls: 0, error: null, reused: false,
  match: { score: 0.4, scored_skill_count: SKILLS.length, unscored_skill_count: 0 },
  report: {
    policy_version: "v12", job_family: FAMILY, core_skill_count: SKILLS.length, module_count: 1, skills: SKILLS,
    priority_order: SKILLS.map((s) => s.skill_id), unscored_skill_ids: [], source_index: {}, database_used: false,
    limitations: [],
  },
} as unknown as SkillGapRun;

const course = (id: string, title: string, skills: string[], guide: Partial<Resource> = {}): Resource => ({
  id, type: "school_course", title, provider: "UW–Madison course", meta: "Check the course guide for terms",
  description: "", skills, url: "https://guide.wisc.edu/courses/comp_sci/", school: SCHOOL, alongside: false, ...guide,
});
/** What /resources lists for this role; the course ids are the catalog's. */
const RESOURCES: Resource[] = [
  { id: "sales-dashboard", type: "project", title: "Sales dashboard", provider: "Project", meta: "Beginner · about 20 hours",
    description: "Model a sales dataset and chart it.", skills: ["data_modeling", "statistics"], url: null, school: null,
    alongside: false },
  { id: "ms-fabric-analytics", type: "certification", title: "Microsoft Certified: Fabric Analytics Engineer Associate",
    provider: "Microsoft", meta: "Intermediate · $165 · Exam fee", description: "", skills: ["data_modeling"],
    url: "https://learn.microsoft.com/", school: null, alongside: false },
  course("uw-cs-320", "COMP SCI 320: Data Science Programming II", ["analytical_scripting"],
    { meta: "4 credits · Last taught Fall 2026", description: "Intermediate approach to Data Science programming using Python.",
      course_code: "COMP SCI 320", credits: "4", last_taught: "Fall 2026" }),
  course("uw-cs-564", "COMP SCI 564: Database Management Systems: Design and Implementation", ["data_modeling"],
    { meta: "4 credits · Last taught Fall 2026", description: "What a database management system is; different data models.",
      course_code: "COMP SCI 564", credits: "4", last_taught: "Fall 2026" }),
  course("uw-stat-240", "STAT 240: Data Science Modeling I", ["statistics", "analytical_scripting"],
    { url: "https://guide.wisc.edu/courses/stat/" }),
];

const takenCourse = (course_id: string): TakenCourse => ({ course_id, source: "manual", created_at: NOW });
