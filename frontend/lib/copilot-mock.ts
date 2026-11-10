/** Local fixtures only. No network, personal résumé, or Agent is used by this adapter. */
export const COPILOT_TOPICS = {
  sql: { label: "SQL & databases", short: "SQL" },
  deployment: { label: "Deployment", short: "Deployment" },
  testing: { label: "Software testing", short: "Testing" },
} as const;
export type CopilotTopic = keyof typeof COPILOT_TOPICS;
export type CopilotSource = { id: string; label: string; excerpt: string };
export type CopilotReply = { text: string; sources: CopilotSource[] };
export type CopilotRequest = {
  question: string;
  history: { role: "user" | "assistant"; text: string }[];
};
export type CopilotResponder = (request: CopilotRequest, signal: AbortSignal) => Promise<CopilotReply>;

const FIXTURES: Record<CopilotTopic, { evidence: string; finding: string; project: string }> = {
  sql: {
    evidence: "Built a task tracker using React and TypeScript. Database queries and schema design are not described.",
    finding: "The sample report has no explicit evidence of SQL queries or relational schema design.",
    project: "Add a small SQL database to the task tracker. Create related tables, implement SELECT and JOIN queries, and document what each query does.",
  },
  deployment: {
    evidence: "Built a working local task-tracking application. Hosting, releases and monitoring are not described.",
    finding: "The sample report has limited evidence of deploying and operating an application.",
    project: "Deploy the task tracker, check its application logs, and write a short release guide that someone else can follow.",
  },
  testing: {
    evidence: "Implemented a task tracker with reusable UI components. Automated tests and edge cases are not described.",
    finding: "The sample report has limited evidence of automated software testing.",
    project: "Add tests for creating, editing and completing a task. Cover invalid input and document one bug the tests help catch.",
  },
};

// Deterministic topic carry-over demonstrates a follow-up without claiming AI understanding.
function topicIn(text: string): CopilotTopic | null {
  if (/deploy|hosting|release/i.test(text)) return "deployment";
  if (/test/i.test(text)) return "testing";
  if (/sql|database/i.test(text)) return "sql";
  return null;
}
export function sampleCopilotReply({ question, history }: CopilotRequest): CopilotReply {
  const topic = topicIn(question) ?? history.filter(m => m.role === "user").map(m => topicIn(m.text)).filter(Boolean).at(-1) ?? "sql";
  const sample = FIXTURES[topic];
  const sources = [
    { id: `sample-resume-${topic}`, label: "Sample résumé · Projects", excerpt: sample.evidence },
    { id: `sample-report-${topic}`, label: `Sample report · ${COPILOT_TOPICS[topic].label}`, excerpt: sample.finding },
  ];
  let text: string;
  if (/reanaly[sz]|re-run|rerun|save|update/i.test(question)) {
    return { text: "This is a local chat demo. I haven’t changed your résumé, saved a plan, or started an analysis. Those actions will be available after the backend is connected.", sources: [] };
  }
  if (/\b(project|build|hours?|week|learn|focus|first|plan)\b/i.test(question)) {
    text = `One project for the sample profile:\n\n${sample.project}\n\nChoose one small milestone, then document the work as résumé evidence. This is an example suggestion; the demo cannot yet personalize a schedule or check a course catalog.`;
  } else if (/\b(already|internship|used|know|experience)\b/i.test(question)) {
    text = `If you already have ${COPILOT_TOPICS[topic].short} experience, describe what you did, where you used it, and the outcome. Missing résumé evidence does not mean you lack the skill.\n\nThis demo uses a fictional résumé. Your message has not changed any saved résumé or analysis.`;
  } else if (/why|gap|evidence|explain|sql|deploy|test/i.test(question)) {
    text = `${sample.finding}\n\n${sample.evidence}\n\nThat is a gap in the available evidence—not a claim that you don’t know the skill. If you have relevant experience, make the work and its outcome explicit in your résumé.`;
  } else {
    return { text: "I’m using scripted examples for this sample profile. Try asking why SQL is a gap, what evidence would demonstrate it, or which project to build. A live Agent is not connected yet.", sources: [] };
  }
  return { text, sources };
}

export const respondToMockCopilot: CopilotResponder = async (request, signal) => {
  await new Promise<void>((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException("Stopped", "AbortError"));
    const abort = () => { clearTimeout(timer); reject(new DOMException("Stopped", "AbortError")); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, 650);
    signal.addEventListener("abort", abort, { once: true });
  });
  return sampleCopilotReply(request);
};
