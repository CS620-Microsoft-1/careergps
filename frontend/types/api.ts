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

/** POST /me/resumes: a confirmed résumé for one destination (role). */
export type ResumeAddRequest = ResumeSubmitRequest & { job_family: JobFamily };

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

/** GET /me/resumes: one saved version, newest first. */
export type ResumeSummary = {
  id: string;
  label: string | null;
  original_filename: string;
  file_type: "pdf" | "docx";
  created_at: string;
  /** The roles matched against this résumé; empty for a version no destination uses. */
  destinations: JobFamily[];
};

/** GET /me/destinations: a role the student added and the résumé it uses. */
export type Destination = {
  job_family: JobFamily;
  resume_id: string;
  original_filename: string;
  created_at: string;
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

export type JobFamily = "software_engineer" | "data_analyst" | "ai_engineer";
export type MarketDemandSkill = {
  skill_id: string;
  module_id: string;
  N: number;
  required_job_count: number;
  preferred_only_job_count: number;
  unspecified_job_count: number;
  required_ratio: number;
  preferred_only_ratio: number;
  unspecified_ratio: number;
};
export type MarketDemandSnapshot = {
  job_family: JobFamily;
  sample_size: number;
  core_skill_count: number;
  source_analysis_version: string;
  snapshot_fingerprint: string;
  skills: MarketDemandSkill[];
  responsibilities_available: false;
  common_responsibilities: [];
  database_used: false;
  snapshot_generated_at: string;
  posting_window: string | null;
  company_coverage: number | null;
  source_description: string;
  coverage_limitations: string[];
};
export type EvidenceProof = { unit_id: string; quote: string };
export type CoreAssessment = {
  kind: "absent" | "knowledge" | "uncertain" | "practice" | "limited_practice";
  evidence_id?: string | null;
  operation_id?: string;
  capability?: { relation: string; quote: string };
  method?: { kind: string; proof: EvidenceProof } | null;
  validation?: {
    kind: string;
    check: EvidenceProof;
    finding: EvidenceProof | null;
    reference: EvidenceProof | null;
    finding_type: string | null;
    reported_value: string | null;
    relation: string;
  } | null;
  reason?: string;
};
export type CoreSkillResult = {
  skill_id: string;
  skill_name: string;
  module_id: string;
  module_name: string;
  resume_evidence_strength: number | null;
  skill_gap: number | null;
  skill_gap_grade: string | null;
  priority: number | null;
  calculation_state: string;
  demand: {
    N: number;
    required_ratio: number;
    preferred_only_ratio: number;
    unspecified_ratio: number;
    required_job_count: number;
    preferred_only_job_count: number;
    unspecified_job_count: number;
  };
  agent_assessment: CoreAssessment | null;
  local_reference_check: { status: string; errors: Array<{ code: string; field: string; detail: string }> };
};
export type ResumeSourceUnit = {
  text: string;
  path: string;
  activity_id: string;
  activity_path?: string;
  activity_context?: Record<string, unknown>;
};
export type CoreSkillGapReport = {
  policy_version: string;
  job_family: JobFamily;
  core_skill_count: number;
  module_count: number;
  skills: CoreSkillResult[];
  priority_order: string[];
  unscored_skill_ids: string[];
  source_index: Record<string, ResumeSourceUnit>;
  database_used: boolean;
  user_id?: string;
  resume_id?: string;
  limitations: string[];
};
/** Demand-weighted résumé evidence (backend: app/services/skill_gaps/match.py). Uncalibrated. */
export type SkillGapMatch = {
  score: number;
  scored_skill_count: number;
  unscored_skill_count: number;
};
export type SkillGapRun = {
  id: string;
  user_id: string;
  resume_id: string;
  status: "queued" | "running" | "completed" | "failed";
  phase: string;
  job_family: JobFamily;
  filename: string;
  resume_hash: string;
  created_at: string;
  completed_at: string | null;
  elapsed_seconds: number;
  model_calls: number;
  report: CoreSkillGapReport | null;
  error: string | null;
  reused: boolean;
  match: SkillGapMatch | null;
};

/** GET /resources (backend: data/resources.yaml). skills holds only the requested role's skills. */
export type ResourceType = "student_org" | "certification" | "online_course" | "school_course" | "project";
export type Resource = {
  id: string;
  type: ResourceType;
  title: string;
  provider: string;
  meta: string;
  description: string;
  skills: string[];
  url: string | null;
  school: string | null;
  alongside: boolean;
};
export type ResourceList = { job_family: JobFamily; resources: Resource[] };

/** GET /plan: saved resources for one role; the browser orders them from the gap ranking. */
export type PlanStatus = "saved" | "done";
export type PlanItem = { resource_id: string; status: PlanStatus; saved_at: string; done_at: string | null };
export type Plan = { job_family: JobFamily; items: PlanItem[] };

/** The stages POST /resumes/analyze/stream reports. "ocr" appears only when a PDF page is an image. */
export type ResumeAnalysisStep = "upload" | "extract" | "ocr" | "classify";

/** What each step reports; which fields are set depends on the step and status. */
export type ResumeStepDetail = {
  /** upload */
  filename?: string;
  file_type?: "pdf" | "docx";
  bytes?: number;
  /** extract done */
  parser?: string;
  characters?: number;
  ocr_pages?: number[];
  /** ocr: one-based page numbers being scanned */
  pages?: number[];
  /** classify done */
  seconds?: number;
  validated?: boolean;
};

export type ResumeStepEvent = {
  type: "step";
  step: ResumeAnalysisStep;
  status: "started" | "done";
  detail: ResumeStepDetail;
};

/** One NDJSON line from POST /resumes/analyze/stream. The last line is a result or an error. */
export type ResumeAnalysisEvent =
  | ResumeStepEvent
  | { type: "result"; data: ResumeAnalysis }
  | { type: "error"; status: number; detail: string };
