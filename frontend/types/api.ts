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

/** POST /resumes/analyze: transient result; the backend stores none of these fields. */
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
