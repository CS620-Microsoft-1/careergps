/** Shared chat contract for local fixtures and the authenticated backend. */
export type CopilotSource = { id: string; label: string; excerpt: string };
export type CopilotReply = { text: string; sources: CopilotSource[] };
export type CopilotRequest = {
  question: string;
  history: { role: "user" | "assistant"; text: string }[];
};
export type CopilotResponder = (request: CopilotRequest, signal: AbortSignal) => Promise<CopilotReply>;
