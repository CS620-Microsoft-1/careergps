import type { AgentStep } from "@/types/agents";

/** The four analysis agents in run order, before any analysis has happened. */
export const INITIAL_PIPELINE: AgentStep[] = [
  {
    name: "Student Profile Agent",
    status: "waiting",
    summary: "Reads your résumé and rates each skill by demonstrated evidence.",
  },
  {
    name: "Market Intelligence Agent",
    status: "waiting",
    summary: "Retrieves recent entry-level postings for your target role.",
  },
  {
    name: "Gap Analysis Agent",
    status: "waiting",
    summary: "Compares market demand with your evidence and ranks the gaps.",
  },
  {
    name: "Action Agent",
    status: "waiting",
    summary: "Builds a roadmap around the work that closes the most gaps.",
  },
];
