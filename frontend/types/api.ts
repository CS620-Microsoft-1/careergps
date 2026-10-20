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
};

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  created_at: string;
};

/** Goal fields are null until onboarding fills them in. */
export type Profile = {
  target_role: string | null;
  experience_level: string | null;
  graduation_year: number | null;
  university: string | null;
  location: string | null;
  onboarding_completed_at: string | null;
};

/** PATCH /me/profile body: only the fields sent change. */
export type ProfileUpdateRequest = {
  full_name?: string;
  target_role?: string;
  experience_level?: string;
  graduation_year?: number;
  university?: string;
  location?: string;
  /** Stamps onboarding_completed_at the first time it is sent. */
  complete_onboarding?: true;
};

/** GET/PUT /me/resume: the reviewed résumé classification the backend keeps (latest only). */
export type SavedResume = {
  filename: string;
  classification: ResumeClassification;
  updated_at: string;
};

/** POST /me body. The email comes from the access token. */
export type AccountCreateRequest = {
  accept_terms: true;
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

/** POST /resumes/analyze: transient result; onboarding saves only the reviewed classification (PUT /me/resume). */
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
