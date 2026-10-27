"use client";

import { useEffect, useState } from "react";

import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { ApiError } from "@/lib/api/client";
import { listDestinations } from "@/lib/api/me";
import { getLatestSkillGapRun } from "@/lib/api/skill-gaps";
import type { Destination, JobFamily, SkillGapRun } from "@/types/api";

export const FAMILIES: JobFamily[] = ["data_analyst", "software_engineer", "ai_engineer"];

/** Setup's role step on its own, for adding another destination. */
export const ADD_DESTINATION_HREF = "/onboarding?step=role";

export type DestinationRun = { status: "loading" | "ready" | "missing" | "error"; run: SkillGapRun | null };
export type Destinations = {
  /** Roles the student has added; the selected role is always included. */
  families: JobFamily[];
  /** Each added role and the résumé it uses. */
  resumes: Partial<Record<JobFamily, Destination>>;
  runs: Record<JobFamily, DestinationRun>;
};

/**
 * The student's destinations (GET /me/destinations), and each one's saved analysis of the résumé
 * it uses. Only reads (GET); starting an analysis is always a click. The selected role uses
 * the live session run instead.
 */
export function useDestinationRuns(): Destinations {
  const { snapshot, family, run } = useSkillGapAnalysis();
  const [resumes, setResumes] = useState<Partial<Record<JobFamily, Destination>>>({});
  const [runs, setRuns] = useState<Partial<Record<JobFamily, DestinationRun>>>({});
  const resumeId = snapshot?.resume_id;

  useEffect(() => {
    if (!resumeId) return;
    let active = true;
    listDestinations().then((destinations) => {
      if (!active) return;
      setResumes(Object.fromEntries(destinations.map((destination) => [destination.job_family, destination])));
      for (const { job_family: key, resume_id } of destinations) {
        getLatestSkillGapRun(key)
          .then((latest) => active && latest.resume_id === resume_id
            && setRuns((all) => ({ ...all, [key]: { status: "ready", run: latest } })))
          .catch((error) => active && setRuns((all) => ({ ...all,
            [key]: { status: error instanceof ApiError && error.status === 404 ? "missing" : "error", run: null } })));
      }
    }).catch(() => {}); // The selected destination still shows from the session.
    return () => { active = false; };
  }, [resumeId]);

  const result = {} as Record<JobFamily, DestinationRun>;
  for (const key of FAMILIES) {
    result[key] = key === family && run ? { status: "ready", run } : runs[key] ?? { status: "loading", run: null };
  }
  return { families: FAMILIES.filter((key) => key === family || resumes[key]), resumes, runs: result };
}
