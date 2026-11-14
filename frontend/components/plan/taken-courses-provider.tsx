"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { useAccount } from "@/components/layout/account-provider";
import { errorMessage } from "@/lib/api/client";
import { getTakenCourses, markCourseTaken, unmarkCourseTaken } from "@/lib/api/student-courses";

type TakenCoursesValue = {
  /** School course ids the student has taken. They stay out of the lists; the plan keeps them. */
  taken: ReadonlySet<string>;
  /** Course ids with a change in flight. */
  pending: ReadonlySet<string>;
  error?: string;
  mark: (courseId: string, source?: "manual" | "resume") => Promise<void>;
  unmark: (courseId: string) => Promise<void>;
  /** The backend recorded it already (a plan item marked done); just show it. */
  noteTaken: (courseId: string) => void;
};

const TakenCoursesContext = createContext<TakenCoursesValue | null>(null);

/** Taken school courses for the signed-in student, for every role. Changes show at once and roll back on failure. */
export function TakenCoursesProvider({ children }: { children: React.ReactNode }) {
  const { status, user } = useAccount();
  // Once the account check is done; "anonymous" covers UI-only development, where the calls just fail.
  const userId = status === "ready" ? user?.id ?? "anonymous" : null;
  const [loaded, setLoaded] = useState<{ userId: string; taken: Set<string> } | null>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!userId) return;
    let active = true;
    getTakenCourses().then((list) => {
      if (active) setLoaded({ userId, taken: new Set(list.courses.map((course) => course.course_id)) });
    }, () => {
      // Lists still work without it; taken courses just aren't hidden.
      if (active) setLoaded({ userId, taken: new Set() });
    });
    return () => { active = false; };
  }, [userId]);

  const taken = useMemo(() => loaded?.userId === userId ? loaded.taken : new Set<string>(), [loaded, userId]);

  const update = useCallback((courseId: string, add: boolean) => setLoaded((current) => {
    if (!current) return current;
    const next = new Set(current.taken);
    if (add) next.add(courseId); else next.delete(courseId);
    return { ...current, taken: next };
  }), []);

  const change = useCallback(async (courseId: string, add: boolean, request: () => Promise<unknown>) => {
    setError(undefined);
    setPending((current) => new Set(current).add(courseId));
    update(courseId, add);
    try {
      await request();
    } catch (failure) {
      update(courseId, !add);
      setError(errorMessage(failure, "That course couldn’t be updated. Try again."));
    } finally {
      setPending((current) => {
        const next = new Set(current);
        next.delete(courseId);
        return next;
      });
    }
  }, [update]);

  const mark = useCallback((courseId: string, source: "manual" | "resume" = "manual") =>
    change(courseId, true, () => markCourseTaken(courseId, source)), [change]);
  const unmark = useCallback((courseId: string) =>
    change(courseId, false, () => unmarkCourseTaken(courseId)), [change]);
  const noteTaken = useCallback((courseId: string) => update(courseId, true), [update]);

  return (
    <TakenCoursesContext value={{ taken, pending, error, mark, unmark, noteTaken }}>
      {children}
    </TakenCoursesContext>
  );
}

export function useTakenCourses() {
  const value = useContext(TakenCoursesContext);
  if (!value) throw new Error("useTakenCourses must be inside TakenCoursesProvider");
  return value;
}
