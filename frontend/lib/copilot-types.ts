import { z } from "zod";

/** Shared chat contract for local fixtures and the authenticated backend. */
export const copilotSourceSchema = z.strictObject({
  id: z.string().min(1).max(200), label: z.string().min(1).max(200), excerpt: z.string().min(1).max(4000),
});
export type CopilotSource = z.infer<typeof copilotSourceSchema>;
export const copilotJobFamilySchema = z.enum(["software_engineer", "data_analyst", "ai_engineer"]);
export const copilotReportIdSchema = z.string().regex(/^[0-9a-f]{32}$/);
/** Browser-only context. Identity is always resolved by the authenticated backend. */
export type CopilotResumeContext = {
  jobFamily: z.infer<typeof copilotJobFamilySchema>;
  resumeId?: string;
  confirmedAt?: string;
  /** Untrusted selector for the report currently shown; the backend verifies ownership and freshness. */
  reportId?: string;
};
export type CopilotReply = { text: string; sources: CopilotSource[]; mode?: "foundry_chat" };
export type CopilotRequest = {
  question: string;
  jobFamily?: CopilotResumeContext["jobFamily"];
  reportId?: string;
  history: { role: "user" | "assistant"; text: string }[];
};
export type CopilotResponder = (request: CopilotRequest, signal: AbortSignal) => Promise<CopilotReply>;

type ResumeReference = { user_id: string; resume_id: string; job_family: CopilotResumeContext["jobFamily"] };
type ReportReference = ResumeReference & { id: string };

/** Only forward the dashboard's report when its visible account, direction and resume agree. */
export function selectedCopilotReportId(userId: string | null, jobFamily: CopilotResumeContext["jobFamily"],
  resume: ResumeReference | null, run: ReportReference | null): string | undefined {
  if (!userId || !resume || !run || resume.user_id !== userId || resume.job_family !== jobFamily
    || run.user_id !== userId || run.job_family !== jobFamily || run.resume_id !== resume.resume_id) return undefined;
  const id = copilotReportIdSchema.safeParse(run.id);
  return id.success ? id.data : undefined;
}
