import type { Page, Route } from "@playwright/test";

import { destinations, market, planItem, resources, resume, run, user } from "../../test/fixtures";
import type {
  CertificationRecommendations,
  JobFamily,
  Plan,
  PlanItem,
  ProjectRecommendations,
  Resource,
  ResumeCourseMatches,
  ResumeSummary,
  TakenCourse,
  TakenCourseList,
} from "../../types/api";

/** Where the app sends API calls; the same default as lib/api/client.ts. */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

type Call = { method: string; path: string; body: unknown };
type Reply = { status: number; json?: unknown };

type Options = {
  planItems?: PlanItem[];
  /** What GET /resources lists; the shared fixtures when left out. */
  resources?: Resource[];
  /** School course ids the student has already marked taken. */
  takenCourses?: string[];
  /** School course ids GET /me/courses/resume-matches finds in the résumé. */
  resumeCourseMatches?: string[];
};

const takenCourse = (course_id: string): TakenCourse => ({ course_id, source: "manual", created_at: "2026-10-02T00:00:00Z" });

/**
 * Answers every FastAPI call from the browser with the shared fixtures, so the end-to-end tests
 * don't need the backend, the database or Azure. Supabase sign-in stays real.
 * Plan items and taken courses live in memory for the test, so a change shows up when they are loaded again.
 */
export async function mockApi(page: Page, options: Options = {}) {
  const items = [...(options.planItems ?? [])];
  const listed = options.resources ?? resources;
  const taken = new Set(options.takenCourses ?? []);
  let held: Promise<void> = Promise.resolve();
  const calls: Call[] = [];
  const basePath = new URL(API_URL).pathname.replace(/\/+$/, "");

  const reply = (method: string, path: string, query: URLSearchParams, body: unknown): Reply => {
    const family = (query.get("job_family") ?? "data_analyst") as JobFamily;
    const ok = (json?: unknown) => ({ status: 200, json });
    const notFound = (detail: string) => ({ status: 404, json: { detail } });
    let match: RegExpMatchArray | null;

    if (method === "GET" && path === "/health/db") return ok({ status: "ok", database: "connected" });
    if (method === "GET" && path === "/me") return ok({ user });
    if (method === "PATCH" && path === "/me") return ok({ ...user, ...(body as object) });
    if (method === "GET" && path === "/me/resume") return ok(resume);
    if (method === "GET" && path === "/me/destinations") return ok(destinations);
    if (method === "GET" && path === "/me/resumes") {
      return ok([{ id: resume.id, label: null, original_filename: resume.original_filename, file_type: resume.file_type,
        created_at: resume.created_at, destinations: ["data_analyst"] }] satisfies ResumeSummary[]);
    }
    if (method === "GET" && path === "/skill-gaps/runs/latest") {
      return family === run.job_family ? ok(run) : notFound("No analysis for this role yet.");
    }
    if (method === "GET" && path === `/skill-gaps/runs/${run.id}`) return ok(run);
    if (method === "GET" && (match = path.match(/^\/skill-gaps\/market\/(\w+)$/))) {
      return ok({ ...market, job_family: match[1] as JobFamily });
    }
    if (method === "GET" && path === "/resources") return ok({ job_family: family, resources: listed });
    if (method === "GET" && path === "/me/courses") {
      return ok({ courses: [...taken].map(takenCourse) } satisfies TakenCourseList);
    }
    if (method === "GET" && path === "/me/courses/resume-matches") {
      return ok({ course_ids: options.resumeCourseMatches ?? [] } satisfies ResumeCourseMatches);
    }
    if (method === "PUT" && (match = path.match(/^\/me\/courses\/([^/]+)$/))) {
      const id = decodeURIComponent(match[1]);
      taken.add(id);
      return ok(takenCourse(id));
    }
    if (method === "DELETE" && (match = path.match(/^\/me\/courses\/([^/]+)$/))) {
      taken.delete(decodeURIComponent(match[1]));
      return { status: 204 };
    }
    if (method === "GET" && path === "/plan") return ok({ job_family: family, items } satisfies Plan);
    if (method === "PUT" && (match = path.match(/^\/plan\/items\/(.+)$/))) {
      const item = planItem(decodeURIComponent(match[1]), (body as { status: PlanItem["status"] }).status);
      items.splice(0, items.length, ...items.filter((i) => i.resource_id !== item.resource_id), item);
      return ok(item);
    }
    if (method === "DELETE" && (match = path.match(/^\/plan\/items\/(.+)$/))) {
      const id = decodeURIComponent(match[1]);
      items.splice(0, items.length, ...items.filter((i) => i.resource_id !== id));
      return { status: 204 };
    }
    if (method === "POST" && path === "/certifications/recommendations") {
      return ok({ job_family: family, skill_gap_run_id: run.id, source: "rules", generated_at: run.created_at,
        recommendations: [] } satisfies CertificationRecommendations);
    }
    if (method === "POST" && path === "/resources/projects/from-skill-gap") {
      return ok({ source: "rules", recommendations: [], no_match_reason: null } satisfies ProjectRecommendations);
    }
    return notFound(`No mock for ${method} ${path}`);
  };

  await page.route((url) => url.href.startsWith(`${API_URL}/`), async (route: Route) => {
    const request = route.request();
    // The app calls the API cross-origin with an Authorization header, so answer CORS too.
    const headers = {
      "access-control-allow-origin": (await request.headerValue("origin")) ?? "*",
      "access-control-allow-headers": "authorization, content-type",
      "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    };
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });

    const url = new URL(request.url());
    const path = url.pathname.slice(basePath.length);
    const body = request.postData() ? request.postDataJSON() : undefined;
    calls.push({ method: request.method(), path, body });
    // Recorded above, answered only once a test that is holding course saves lets go.
    if (request.method() === "PUT" && path.startsWith("/me/courses/")) await held;
    const { status, json } = reply(request.method(), path, url.searchParams, body);
    return json === undefined ? route.fulfill({ status, headers }) : route.fulfill({ status, headers, json });
  });

  /** Keep PUT /me/courses/{id} unanswered until the returned function is called. */
  const holdCourseSaves = () => {
    let release = () => {};
    held = new Promise<void>((resolve) => { release = resolve; });
    return release;
  };

  return { items, calls, taken, holdCourseSaves };
}
