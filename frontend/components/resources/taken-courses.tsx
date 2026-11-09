"use client";

import { useEffect, useState } from "react";
import { Check, FileSearch, GraduationCap, LoaderCircle } from "lucide-react";

import { useAccount } from "@/components/layout/account-provider";
import { useTakenCourses } from "@/components/plan/taken-courses-provider";
import { Button } from "@/components/ui/button";
import { getResumeCourseMatches } from "@/lib/api/student-courses";
import { courseCode } from "@/lib/career";
import type { JobFamily, Resource } from "@/types/api";

/** Mark taken / Taken, on a school course card. Marking hides the course from the lists. */
export function TakenButton({ resource, onMarked }: { resource: Resource; onMarked?: (resource: Resource) => void }) {
  const { taken, pending, mark, unmark } = useTakenCourses();
  const isTaken = taken.has(resource.id);
  const busy = pending.has(resource.id);
  return (
    <Button type="button" size="sm" variant={isTaken ? "accent" : "ghost"} aria-pressed={isTaken} disabled={busy}
      className="-my-1 shrink-0"
      onClick={() => {
        if (isTaken) {
          void unmark(resource.id);
        } else {
          void mark(resource.id);
          onMarked?.(resource);
        }
      }}>
      {busy ? <LoaderCircle data-icon="inline-start" className="motion-safe:animate-spin" />
        : isTaken ? <Check data-icon="inline-start" /> : <GraduationCap data-icon="inline-start" />}
      {isTaken ? "Taken" : "Mark taken"}
    </Button>
  );
}

/** Shown after a course is marked taken and drops out of the list. */
export function TakenUndo({ resource, onClose }: { resource: Resource; onClose: () => void }) {
  const { unmark } = useTakenCourses();
  return (
    <div role="status" className="mb-4 flex flex-wrap items-center gap-3 rounded-xl bg-success-soft px-4 py-2.5 text-sm">
      <Check aria-hidden className="size-4" />
      <p className="min-w-0 flex-1">Marked <b>{courseCode(resource)}</b> as taken. We’ll hide it from your lists.</p>
      <Button type="button" size="sm" variant="raised" onClick={() => { void unmark(resource.id); onClose(); }}>Undo</Button>
    </div>
  );
}

const DISMISSED_KEY = "careergps:resume-course-matches:dismissed";

function readDismissed(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(DISMISSED_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function writeDismissed(ids: string[]) {
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify(ids));
  } catch {
    // Private mode or blocked storage: the prompt just comes back next time.
  }
}

/**
 * Course codes found in the role's résumé. Nothing is saved until the student presses
 * "Mark them taken"; "Not now" hides these courses in this browser only.
 */
export function ResumeCourseMatches({ family, courses }: { family: JobFamily; courses: Resource[] }) {
  const { status } = useAccount();
  const { taken, mark } = useTakenCourses();
  const [found, setFound] = useState<{ family: JobFamily; ids: string[] } | null>(null);
  const [dismissed, setDismissed] = useState<string[]>([]);

  useEffect(() => {
    if (status !== "ready") return;
    let active = true;
    getResumeCourseMatches(family).then((matches) => {
      if (active) {
        setDismissed(readDismissed());
        setFound({ family, ids: matches.course_ids });
      }
    }, () => undefined);  // Only a suggestion; skip it when it fails.
    return () => { active = false; };
  }, [family, status]);

  const ids = found?.family === family ? found.ids : [];
  const shown = courses.filter((course) => ids.includes(course.id) && !taken.has(course.id) && !dismissed.includes(course.id));
  if (!shown.length) return null;
  const names = shown.map(courseCode);
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl bg-accent px-4 py-3 text-sm">
      <FileSearch aria-hidden className="size-4.5" />
      <p className="min-w-0 flex-1 basis-60">
        Found in your résumé: <b>{names.join(", ")}</b>. Mark {shown.length === 1 ? "it" : "them"} as taken?
      </p>
      <div className="flex gap-2">
        <Button type="button" size="sm" onClick={() => { for (const course of shown) void mark(course.id, "resume"); }}>
          Mark {shown.length === 1 ? "it" : "them"} taken
        </Button>
        <Button type="button" size="sm" variant="raised" onClick={() => {
          const next = [...new Set([...dismissed, ...shown.map((course) => course.id)])];
          writeDismissed(next);
          setDismissed(next);
        }}>Not now</Button>
      </div>
    </div>
  );
}
