import { z } from "zod";
import { apiPost } from "./client.ts";
import type { CopilotRequest, CopilotResponder } from "../copilot-types.ts";

/** Local scripted mode is an explicit opt-in, never an automatic fallback after an API error. */
export const LOCAL_COPILOT = process.env.NEXT_PUBLIC_COPILOT_MODE === "local";

const responseSchema = z.object({
  text: z.string().trim().min(1).max(8000),
  sources: z.array(z.object({
    id: z.string().min(1).max(200), label: z.string().min(1).max(200), excerpt: z.string().min(1).max(4000),
  })).max(10),
  intent: z.enum(["explain_gap", "learning_advice", "clarify", "general", "unsupported_action", "tool_error"]),
  mode: z.literal("foundry_mock"),
  analysisId: z.literal("sample-swe-v1"),
});

/** Retain the newest complete messages; older history stays visible in browser storage. */
export function boundedCopilotRequest(request: CopilotRequest): CopilotRequest {
  const history = request.history.slice(-20);
  let length = request.question.length + history.reduce((total, turn) => total + turn.text.length, 0);
  while (history.length && length > 24000) length -= history.shift()!.text.length;
  return { question: request.question, history };
}

export const respondToCopilot: CopilotResponder = async (request, signal) => {
  const result = await apiPost<unknown>("/copilot/chat", {
    json: boundedCopilotRequest(request), signal, timeoutMs: 135000,
  });
  return responseSchema.parse(result);
};
