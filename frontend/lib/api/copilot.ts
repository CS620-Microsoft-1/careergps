import { z } from "zod";
import { ApiError, apiGet, apiPost } from "./client.ts";
import type { CopilotRequest, CopilotResponder } from "../copilot-types.ts";
import { copilotJobFamilySchema, copilotReportIdSchema, copilotSourceSchema } from "../copilot-types.ts";

const responseSchema = z.strictObject({
  text: z.string().min(1).max(8000),
  sources: z.array(copilotSourceSchema).max(8),
  mode: z.literal("foundry_chat"),
  jobFamily: copilotJobFamilySchema,
});

const capabilitiesSchema = z.strictObject({ dataReadsEnabled: z.boolean() });

/** Uses the existing CareerGPS login; capability lookup never starts a model request. */
export async function getCopilotCapabilities(expectedUserId: string, signal?: AbortSignal) {
  return capabilitiesSchema.parse(await apiGet<unknown>("/copilot/capabilities", { signal, expectedUserId }));
}

/** Retain recent completed turns without splitting a user/assistant pair. */
export function boundedCopilotRequest(request: CopilotRequest): CopilotRequest {
  const history = request.history.slice(-20);
  if (history[0]?.role === "assistant") history.shift();
  let length = request.question.length + history.reduce((total, turn) => total + turn.text.length, 0);
  while (history.length && length > 24000) {
    length -= history.shift()!.text.length;
    if (history[0]?.role === "assistant") length -= history.shift()!.text.length;
  }
  return { question: request.question, history, ...(request.jobFamily ? { jobFamily: request.jobFamily } : {}),
    ...(request.reportId !== undefined ? { reportId: copilotReportIdSchema.parse(request.reportId) } : {}) };
}

export function createCopilotResponder(expectedUserId: string): CopilotResponder {
  return async (request, signal) => {
    if (!expectedUserId) throw new ApiError(409, "Account unavailable", "Sign in before using Copilot.");
    if (!request.jobFamily) throw new ApiError(409, "No selected direction", "Select a career direction before using Copilot.");
    const bounded = boundedCopilotRequest(request);
    const result = await apiPost<unknown>("/copilot/chat", {
      json: { question: bounded.question, history: bounded.history, jobFamily: request.jobFamily,
        ...(bounded.reportId ? { reportId: bounded.reportId } : {}) }, signal, timeoutMs: 135000, expectedUserId,
    });
    const reply = responseSchema.parse(result);
    if (reply.jobFamily !== request.jobFamily) {
      throw new Error("Copilot returned a different career direction");
    }
    return reply;
  };
}
