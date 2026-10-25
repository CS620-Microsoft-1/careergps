"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";

import { ApiError } from "@/lib/api/client";
import { getSkillGapRun, startSkillGapRun } from "@/lib/api/skill-gaps";
import {
  clearQueuedSkillGapAnalysis, forgetRun, getQueuedSkillGapAnalysis, getSavedRun,
  loadConfirmedResume, resumeHash, saveRun, saveSnapshotFamily,
} from "@/lib/confirmed-resume";
import { SkillGapSession, type SkillGapSessionState } from "@/lib/skill-gap-session";

type SkillGapContextValue = SkillGapSessionState & Pick<SkillGapSession, "analyze" | "changeFamily">;
const SkillGapContext = createContext<SkillGapContextValue | null>(null);

export function SkillGapProvider({ children }: { children: React.ReactNode }) {
  const [session] = useState(() => new SkillGapSession({
    loadSnapshot: loadConfirmedResume,
    hashResume: (snapshot) => resumeHash(snapshot.reviewed_resume),
    getSavedRun, saveRun, forgetRun,
    hasIntent: getQueuedSkillGapAnalysis,
    clearIntent: clearQueuedSkillGapAnalysis,
    saveFamily: saveSnapshotFamily,
    getRun: getSkillGapRun,
    startRun: (snapshot, family, force) => startSkillGapRun({ confirmed: true,
      reviewed_resume: snapshot.reviewed_resume, job_family: family,
      filename: snapshot.filename, confirmed_at: snapshot.confirmed_at, force }),
    isNotFound: (error) => error instanceof ApiError && error.status === 404,
    errorMessage: (error) => error instanceof ApiError ? error.detail ?? error.message
      : error instanceof Error ? error.message : "The local analysis could not be loaded. Try again.",
    now: Date.now,
    setTimer: (callback, delay) => setTimeout(callback, delay),
    clearTimer: (timer) => clearTimeout(timer),
  }));
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getServerSnapshot);
  useEffect(() => session.connect(), [session]);

  return <SkillGapContext value={{ ...state, analyze: session.analyze, changeFamily: session.changeFamily }}>
    {children}
  </SkillGapContext>;
}

export function useSkillGapAnalysis() {
  const value = useContext(SkillGapContext);
  if (!value) throw new Error("Skill Gap views must be inside SkillGapProvider");
  return value;
}
