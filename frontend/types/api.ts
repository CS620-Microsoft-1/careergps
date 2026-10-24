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

/** GET /me, POST /me (backend: app/schemas/me.py). user is null until onboarding is finished. */
export type MeResponse = {
  user: User | null;
};

/** The users row: created at the end of onboarding, together with the first résumé. */
export type User = {
  id: string;
  primary_email: string;
  first_name: string;
  last_name: string;
  full_name: string | null;
  target_role: string;
  experience_level: string;
  graduation_year: number;
  university: string;
  preferred_location: string;
  resume_emails: string[];
  phones: string[];
  current_location: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  website_url: string | null;
  active_resume_id: string | null;
  created_at: string;
};

/** A résumé confirmed on the review page, with how POST /resumes/analyze read it. */
export type ResumeSubmitRequest = {
  original_filename: string;
  parser: string;
  ocr_pages: number[];
  agent_name: string;
  classification: ResumeClassification;
};

/** The career goal asked in onboarding. */
export type Goals = {
  target_role: string;
  experience_level: string;
  graduation_year: number;
  preferred_location: string;
};

/** Asked in onboarding: the name (the résumé's own is kept as full_name) and the university,
 * which the review page pre-fills from the résumé. */
export type PersonalDetails = {
  first_name: string;
  last_name: string;
  university: string;
};

/** POST /me body: finishes onboarding. The email comes from the access token. */
export type AccountCreateRequest = Goals & PersonalDetails & {
  accept_terms: true;
  resume: ResumeSubmitRequest;
};

/** GET /me/resume, POST /me/resumes: a confirmed résumé version. */
export type SavedResume = {
  id: string;
  original_filename: string;
  file_type: "pdf" | "docx";
  classification: ResumeClassification;
  created_at: string;
};

export type ResumeFieldValue = string | null | string[];
export type ResumeRecord = Record<string, ResumeFieldValue>;

export type ResumeClassification = {
  personal_information: ResumeRecord;
  research_interests: string[];
  education: ResumeRecord[];
  work_experience: ResumeRecord[];
  research_experience: ResumeRecord[];
  projects: ResumeRecord[];
  technical_skills: string[];
  languages: ResumeRecord[];
  publications: ResumeRecord[];
  awards_honors: ResumeRecord[];
  certifications: ResumeRecord[];
  leadership_activities: ResumeRecord[];
  other: ResumeRecord[];
};

/** POST /resumes/analyze: transient result; onboarding saves the reviewed classification (POST /me or POST /me/resumes). */
export type ResumeAnalysis = {
  filename: string;
  extraction: {
    parser: string;
    ocr_pages: number[];
    characters: number;
    seconds: number;
    text: string;
  };
  agent: {
    name: string;
    seconds: number;
    validated: boolean;
  };
  classification: ResumeClassification;
};
