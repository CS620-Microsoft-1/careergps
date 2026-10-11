"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { API_BASE_URL, ApiError } from "@/lib/api/client";
import { getDatabaseHealth } from "@/lib/api/health";

export type BackendStatus = "checking" | "connected" | "database-down" | "unreachable";

type BackendStatusContextValue = {
  status: BackendStatus;
  /** The API address the frontend is using (NEXT_PUBLIC_API_URL). */
  apiUrl: string;
  /** Check again now, e.g. from a "try again" action. */
  recheck: () => void;
};

const BackendStatusContext = createContext<BackendStatusContextValue | null>(null);

function toStatus(error: unknown): BackendStatus {
  return error instanceof ApiError && error.status === 503 ? "database-down" : "unreachable";
}

/**
 * Owns the backend health check so every status badge shares one request and one answer.
 * Checks when the app shell loads and whenever the tab regains focus.
 */
export function BackendStatusProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<BackendStatus>("checking");
  // Checks can overlap (e.g. refocusing twice quickly); only the newest one may set the status.
  const latestCheckRef = useRef(0);

  const recheck = useCallback(async () => {
    const checkId = ++latestCheckRef.current;
    let next: BackendStatus;
    try {
      await getDatabaseHealth();
      next = "connected";
    } catch (error) {
      next = toStatus(error);
    }
    if (checkId === latestCheckRef.current) setStatus(next);
  }, []);

  useEffect(() => {
    void recheck();
    const onFocus = () => void recheck();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [recheck]);

  const value = useMemo(
    () => ({ status, apiUrl: API_BASE_URL, recheck: () => void recheck() }),
    [status, recheck],
  );

  return <BackendStatusContext value={value}>{children}</BackendStatusContext>;
}

export function useBackendStatus() {
  const ctx = useContext(BackendStatusContext);
  if (!ctx) throw new Error("useBackendStatus must be used inside <BackendStatusProvider>");
  return ctx;
}
