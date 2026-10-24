/** Prototype contract; replace respondToCopilot with apiPost when the API is ready. */
export type CopilotSource = { label: string; excerpt: string };
export type CopilotReply = { text: string; sources: CopilotSource[] };
export type CopilotTurn = { role: "user" | "assistant"; text: string };
export type CopilotRequest = {
  question: string;
  history: CopilotTurn[];
  analysisId: string;
};
export type CopilotResponder = (request: CopilotRequest) => Promise<CopilotReply>;
export const DEMO_ANALYSIS_ID = "demo-swe-sql";
export const COPILOT_QUESTIONS = [
  "Why was this skill flagged as a gap?",
  "What should I focus on first?",
  "What evidence would show that I already have this skill?",
] as const;
const resume: CopilotSource = {
  label: "Sample resume · Projects",
  excerpt: "Built a task tracker using React and TypeScript. No SQL or database work is described.",
};
const requirement: CopilotSource = {
  label: "Sample SWE role · Requirements",
  excerpt: "Use SQL to query relational databases and combine data across tables.",
};
const gap: CopilotSource = {
  label: "Sample gap analysis · SQL",
  excerpt: "SQL: priority for review. Target-role requirement has no explicit supporting evidence in the sample resume.",
};
/** Scripted demo only: no model, retrieval, network call, or real profile data. */
export const respondToCopilot: CopilotResponder = async ({ question, history, analysisId }) => {
  if (analysisId !== DEMO_ANALYSIS_ID) throw new Error("Only the sample analysis is supported.");
  await new Promise<void>((resolve) => setTimeout(resolve, 650));
  const text = question.toLowerCase();
  if (/evidence|prove|demonstrate|already|internship|\bused\b|\bknow\b/.test(text)) {
    return {
      text: "For this sample SQL gap, useful evidence would be a project or internship example where you wrote queries, joined tables, or designed a relational schema. Explain what you did and link to code or describe a concrete result.\n\nFor example: ‘Used SQL joins to combine customer and order data for a reporting dashboard.’ Only include this if it accurately describes your work.\n\nIf you already used SQL, that may mean the resume is missing evidence. This prototype cannot verify your experience or update your saved analysis.",
      sources: [resume, requirement],
    };
  }
  if (/focus|first|priorit|start|learn|improve/.test(text)) {
    return {
      text: "First, check whether you already have SQL experience that is missing from your resume. If you do, describe it clearly before investing time in another course.\n\nIf SQL is new to you, start with SELECT, filtering, JOINs, and GROUP BY. Then add a small relational database to your existing task tracker and document the queries you wrote.\n\nThis is a suggested next step for the sample profile, not a ranking based on your actual background or the live job market.",
      sources: [gap, resume, requirement],
    };
  }
  if (/why|flag|gap|\bsql\b/.test(text)) {
    return {
      text: "SQL was flagged in the sample analysis because the sample SWE role asks for relational database queries, while the sample resume describes React and TypeScript without mentioning SQL.\n\nThat is a gap in the available evidence. It does not establish that you lack the skill. If you have used SQL in a class, project, or internship, you could add that experience to your profile for a future reassessment.",
      sources: [requirement, resume, gap],
    };
  }
  return {
    text: `${history.length ? "We are discussing SQL in the sample SWE analysis. " : "This demo uses a sample SWE profile with a SQL evidence gap. "}I have scripted answers for why SQL was flagged, what to focus on first, and what evidence could demonstrate the skill. Try one of the suggested questions below. Other questions will be supported when the backend is connected.`,
    sources: [],
  };
};
