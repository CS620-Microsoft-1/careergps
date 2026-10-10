export type AgentStatus = "waiting" | "running" | "complete";

/** One stage of the CareerGPS analysis pipeline, as shown to the student. */
export type AgentStep = {
  name: string;
  status: AgentStatus;
  /** What the agent did, or will do, in plain language. */
  summary: string;
};
