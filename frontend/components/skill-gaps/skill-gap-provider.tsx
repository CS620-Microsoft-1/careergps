"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";

import { ApiError } from "@/lib/api/client";
import { getMe, getSavedResume } from "@/lib/api/me";
import { getLatestSkillGapRun, getSkillGapRun, startSkillGapRun } from "@/lib/api/skill-gaps";
import { consumeSkillGapIntent, profileForAnalysis, type SkillGapProfile } from "@/lib/skill-gap-profile";
import { SkillGapSession, type SkillGapSessionState } from "@/lib/skill-gap-session";

type SkillGapContextValue = SkillGapSessionState & Pick<SkillGapSession, "analyze" | "changeFamily" | "reload">;
const SkillGapContext = createContext<SkillGapContextValue | null>(null);

function createSession() {
  return new SkillGapSession({
    loadProfile: async (family) => {
      const [{ user }, resume] = await Promise.all([getMe(), getSavedResume(family)]);
      return user && resume ? profileForAnalysis(user, resume, family) : null;
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
  });
}

/**
 * One session per browser tab, shared by the app shell and the setup route page: going from the route
 * summary to Home shows the run already loaded instead of loading it again. Sign-out reloads the page,
 * which starts a new one. The server renders with its own, which never loads anything.
 */
let shared: SkillGapSession | null = null;
const getSession = () => typeof window === "undefined" ? createSession() : (shared ??= createSession());

/** Setup saved this destination and résumé: the route page waits for them, not the ones shown before. */
export function expectSkillGapProfile(profile: SkillGapProfile) {
  getSession().expect(profile);
}

export function SkillGapProvider({ children }: { children: React.ReactNode }) {
  const [session] = useState(getSession);
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getServerSnapshot);
  useEffect(() => session.connect(), [session]);
  return <SkillGapContext value={{ ...state, analyze: session.analyze, changeFamily: session.changeFamily, reload: session.reload }}>{children}</SkillGapContext>;
}

export function useSkillGapAnalysis() {
  const value = useContext(SkillGapContext);
  if (!value) throw new Error("Skill Gap views must be inside SkillGapProvider");
  return value;
}
