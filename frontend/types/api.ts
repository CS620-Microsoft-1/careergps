// Response shapes returned by the CareerGPS API (backend/app/api/routes/).
// Hand-written for now; to be replaced by types generated from the API's /openapi.json.

/** GET /health: the API process is running. */
export type HealthResponse = {
  status: "ok";
};

/** GET /health/db: the API can reach the database. A 503 means it can't. */
export type DatabaseHealthResponse = {
  status: "ok";
  database: "connected";
};

/** GET /me, POST /me (backend: app/schemas/me.py). user/profile are null until POST /me succeeds. */
export type MeResponse = {
  user: User | null;
  profile: Profile | null;
  latest_resume: ResumeSummary | null;
};

export type User = {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
};

export type Profile = {
  target_role: string;
  experience_level: string;
  graduation_year: number;
  university: string;
  location: string | null;
  phone: string | null;
  links: string[] | null;
  onboarding_completed_at: string | null;
};

/** POST /me body: the sign-up fields. */
export type AccountCreateRequest = {
  full_name: string;
  target_role: string;
  graduation_year: number;
  university: string;
  experience_level: string;
  accept_terms: true;
};

/** Résumé parsing states (SPEC-001 §6). */
export type ResumeStatus = "pending" | "parsing" | "parsed" | "confirmed" | "failed";

export type ResumeErrorCode = "no_text" | "llm_invalid_output" | "llm_unavailable" | "internal";

/** POST /resumes, POST /resumes/{id}/retry (backend: app/schemas/resume.py). */
export type ResumeSummary = {
  id: string;
  status: ResumeStatus;
  error_code: ResumeErrorCode | null;
  original_filename: string;
  created_at: string;
};

/** GET /resumes/{id}. parsed_data is set once status is "parsed". */
export type Resume = ResumeSummary & {
  parsed_data: ResumeData | null;
};

export type SkillCategory = "language" | "framework" | "tool" | "other";

/** What the LLM extracted; edited by the user and sent back to POST /resumes/{id}/confirm. */
export type ResumeData = {
  contact: {
    full_name: string | null;
    email: string | null;
    phone: string | null;
    location: string | null;
    links: string[];
  };
  education: {
    school: string;
    degree: string | null;
    field_of_study: string | null;
    start_date: string | null;
    end_date: string | null;
    gpa: string | null;
  }[];
  experience: {
    company: string;
    title: string | null;
    location: string | null;
    start_date: string | null;
    end_date: string | null;
    is_current: boolean;
    bullets: string[];
  }[];
  projects: {
    name: string;
    description: string | null;
    url: string | null;
    technologies: string[];
  }[];
  skills: { name: string; category: SkillCategory }[];
};
