"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";

import { ApiError } from "@/lib/api/client";
import { getMe, getSavedResume } from "@/lib/api/me";
import { getLatestSkillGapRun, getSkillGapRun, startSkillGapRun } from "@/lib/api/skill-gaps";
import { consumeSkillGapIntent, profileForAnalysis } from "@/lib/skill-gap-profile";
import { SkillGapSession, type SkillGapSessionState } from "@/lib/skill-gap-session";

type SkillGapContextValue = SkillGapSessionState & Pick<SkillGapSession, "analyze" | "changeFamily">;
const SkillGapContext = createContext<SkillGapContextValue | null>(null);

export function SkillGapProvider({ children }: { children: React.ReactNode }) {
  const [session] = useState(() => new SkillGapSession({
    loadProfile: async () => {
      const [{ user }, resume] = await Promise.all([getMe(), getSavedResume()]);
      return user && resume ? profileForAnalysis(user, resume) : null;
    },
    consumeIntent: consumeSkillGapIntent,
    getLatest: getLatestSkillGapRun,
    getRun: getSkillGapRun,
    startRun: (job_family, force) => startSkillGapRun({ job_family, force }),
    isNotFound: (error) => error instanceof ApiError && error.status === 404,
    errorMessage: (error) => error instanceof ApiError ? error.detail ?? error.message
      : error instanceof Error ? error.message : "The analysis could not be loaded. Try again.",
    now: Date.now,
    setTimer: (callback, delay) => setTimeout(callback, delay),
    clearTimer: (timer) => clearTimeout(timer),
  }));
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getServerSnapshot);
  useEffect(() => session.connect(), [session]);
  return <SkillGapContext value={{ ...state, analyze: session.analyze, changeFamily: session.changeFamily }}>{children}</SkillGapContext>;
}

export function useSkillGapAnalysis() {
  const value = useContext(SkillGapContext);
  if (!value) throw new Error("Skill Gap views must be inside SkillGapProvider");
  return value;
}
