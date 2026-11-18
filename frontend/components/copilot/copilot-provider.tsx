"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import type { CopilotResumeContext } from "@/lib/copilot-types";
import { selectedCopilotReportId } from "@/lib/copilot-types";
import { useAccount } from "@/components/layout/account-provider";
import { CopilotSession, createCopilotStorage, type CopilotState } from "@/lib/copilot-session";

import { createCopilotResponder, getCopilotCapabilities } from "@/lib/api/copilot";

const CopilotContext = createContext<{ session: CopilotSession; state: CopilotState; sessionOnly: boolean; dataReadsEnabled: boolean } | null>(null);

export function CopilotProvider({ children }: { children: React.ReactNode }) {
  const { authUserId, status } = useAccount();
  const { snapshot, family, loaded, run } = useSkillGapAnalysis();
  const knownResume = snapshot?.user_id === authUserId && snapshot?.job_family === family ? snapshot : null;
  const reportId = selectedCopilotReportId(authUserId, family, knownResume, run);
  const resumeContext: CopilotResumeContext | null = status === "ready" && loaded && authUserId
    ? { jobFamily: family, ...(knownResume ? { resumeId: knownResume.resume_id, confirmedAt: knownResume.confirmed_at } : {}),
      ...(reportId ? { reportId } : {}) } : null;
  const unavailableReason = status !== "ready" ? "Loading your account. Please wait."
    : !loaded ? "Loading your selected direction. Please wait."
    : "Sign in to use Copilot for the selected direction.";
  const owner = authUserId ? `user:${authUserId}` : null;
  return <OwnerConversation key={owner ?? "unverified"} owner={owner} userId={authUserId} ready={status === "ready"} resumeContext={resumeContext} unavailableReason={resumeContext ? null : unavailableReason}>{children}</OwnerConversation>;
}

function OwnerConversation({ owner, userId, ready, resumeContext, unavailableReason, children }: {
  owner: string | null; userId: string | null; ready: boolean; resumeContext: CopilotResumeContext | null;
  unavailableReason: string | null; children: React.ReactNode;
}) {
  const [session] = useState(() => new CopilotSession({ ...createCopilotStorage(owner), respond: createCopilotResponder(userId ?? "") }));
  const [dataReadsEnabled, setDataReadsEnabled] = useState(false);
  useEffect(() => {
    if (!ready || !userId) return;
    const controller = new AbortController();
    let active = true;
    void getCopilotCapabilities(userId, controller.signal).then(capabilities => {
      if (active) setDataReadsEnabled(capabilities.dataReadsEnabled);
    }).catch(() => {
      if (active) setDataReadsEnabled(false);
    });
    return () => { active = false; controller.abort(); };
  }, [userId, ready]);
  const resumeId = resumeContext?.resumeId;
  const confirmedAt = resumeContext?.confirmedAt;
  const jobFamily = resumeContext?.jobFamily;
  const reportId = resumeContext?.reportId;
  useEffect(() => {
    session.setResumeContext(jobFamily ? { jobFamily, ...(resumeId ? { resumeId } : {}), ...(confirmedAt ? { confirmedAt } : {}),
      ...(reportId ? { reportId } : {}) } : null, unavailableReason);
  }, [session, resumeId, confirmedAt, jobFamily, reportId, unavailableReason]);
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getServerSnapshot);
  useEffect(() => {
    if (ready) session.initialize();
    return () => session.cancel();
  }, [session, ready]);
  return <CopilotContext value={{ session, state, sessionOnly: !owner, dataReadsEnabled: ready && dataReadsEnabled }}>{children}</CopilotContext>;
}

export function useCopilot() {
  const value = useContext(CopilotContext);
  if (!value) throw new Error("useCopilot must be inside CopilotProvider");
  return value;
}
