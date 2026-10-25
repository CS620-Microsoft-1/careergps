"use client";

import Link from "next/link";
import { CircleCheck, ChevronRight, LoaderCircle } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { groupProfileSkills } from "@/lib/profile-skills";
import { getResumeProfile } from "@/lib/resume-profile";
import { SKILL_LABELS } from "@/lib/skill-gap-labels";
import type { CoreSkillResult } from "@/types/api";

const COLUMNS = [
  { key: "strong", title: "Strong", dot: "bg-success", empty: "No skills in this evidence band yet." },
  { key: "some", title: "Some experience", dot: "bg-warning-fill", empty: "No skills in this evidence band yet." },
  { key: "absent", title: "Not yet demonstrated", dot: "bg-danger", empty: "No skills are missing selected résumé evidence." },
] as const;

export function ProfileWorkspace() {
  const { loaded, snapshot, family, run, submitting, restoring, error } = useSkillGapAnalysis();
  const profile = getResumeProfile(snapshot);
  const report = run?.status === "completed" && run.report?.job_family === family ? run.report : null;
  const groups = groupProfileSkills(report);
  const busy = submitting || run?.status === "queued" || run?.status === "running";
  const failed = run?.status === "failed";
  const statusText = !loaded ? "Loading your reviewed profile…"
    : restoring ? "Restoring your saved analysis…"
    : busy ? "Your résumé is confirmed. Skill evidence analysis is in progress."
    : failed ? "Your résumé is confirmed, but skill analysis could not finish."
    : report ? `Skill evidence for ${profile.targetRole}. These groups describe your résumé, not your ability.`
    : snapshot ? "Your résumé is confirmed. Analyze your skill gaps to see the evidence groups."
    : "Review and confirm your résumé to see your profile and skill evidence.";

  return <>
    <PageHeader title="Your Profile" description="What CareerGPS found in your résumé." />
    <Card className="mb-4">
      <CardContent className="flex flex-wrap items-center gap-4">
        <Avatar size="lg"><AvatarFallback>{loaded ? profile.initials : "…"}</AvatarFallback></Avatar>
        <div className="min-w-0 flex-1 basis-48">
          <h2 className="text-base">{loaded ? profile.name : "Loading profile…"}</h2>
          <p className="break-words text-muted-foreground">{!loaded ? "Loading your reviewed résumé…"
            : snapshot ? [profile.institution, profile.filename].filter(Boolean).join(" · ") : "No résumé confirmed yet"}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge>{profile.targetRole ?? "Target role not set"}</Badge>
            <Badge>{profile.graduationYear ? `Class of ${profile.graduationYear}` : "Graduation year not set"}</Badge>
          </div>
        </div>
        {loaded && <Button asChild variant="outline"><Link href={snapshot ? "/onboarding?edit=1" : "/onboarding"}>
          {snapshot ? "Review résumé" : "Upload résumé"}
        </Link></Button>}
      </CardContent>
    </Card>

    <div className="mb-4 flex flex-wrap items-center gap-2.5 rounded-lg bg-accent px-3.5 py-2.5 text-control text-accent-foreground">
      {busy || restoring || !loaded ? <LoaderCircle aria-hidden className="size-4 shrink-0 motion-safe:animate-spin" />
        : <CircleCheck aria-hidden className="size-4 shrink-0" />}
      <p role="status" className="min-w-0 flex-1 basis-56">{statusText}</p>
      {snapshot && !report && loaded && <Link href="/dashboard" className="inline-flex items-center gap-1 text-xs font-semibold hover:underline">
        {busy || restoring ? "View analysis progress" : "Open dashboard"}<ChevronRight aria-hidden className="size-3.5" />
      </Link>}
    </div>

    {(error || failed) && <div role="alert" className="mb-4 rounded-lg border border-warning/30 bg-warning-soft px-3.5 py-3 text-sm">
      <p>{error ?? run?.error ?? "The analysis is unavailable. Your confirmed résumé is still here."}</p>
      <Link href="/dashboard" className="mt-1 inline-block font-medium text-primary hover:underline">Return to dashboard</Link>
    </div>}
    {groups.pending.length > 0 && <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-warning/30 bg-warning-soft px-3.5 py-3 text-sm">
      <p>{groups.pending.length} {groups.pending.length === 1 ? "skill needs" : "skills need"} review and {groups.pending.length === 1 ? "has" : "have"} no assigned score. These are kept separate from missing evidence.</p>
      <Link href="/gaps" className="font-medium text-primary hover:underline">Review evidence</Link>
    </div>}

    <div className="grid items-start gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {COLUMNS.map(({ key, title, dot, empty }) => <Card key={key} size="sm">
        <CardContent>
          <h3 className="flex items-center gap-2 text-sm"><span aria-hidden className={`size-2 rounded-full ${dot}`} />{title}
            <span className="ml-auto font-normal text-muted-foreground">{report ? groups[key].length : "—"}</span>
          </h3>
          {report && groups[key].length > 0 ? <ul className="mt-3 divide-y divide-line-soft border-t border-line-soft">
            {groups[key].map((skill) => <ProfileSkill key={skill.skill_id} skill={skill} />)}
          </ul> : <p className="mt-3 border-t border-line-soft pt-3 text-control text-muted-foreground">
            {report ? empty : busy || restoring ? "Your skill evidence will appear when the current analysis completes."
              : snapshot ? "Run your skill gap analysis to see assessed skills here." : "Skills will appear here after your résumé is confirmed and analyzed."}
          </p>}
        </CardContent>
      </Card>)}
    </div>
    {report && <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
      Groups use your existing gap grades: Strong — A, A−, B+; Some experience — B, C, D with positive evidence;
      Not yet demonstrated — F with zero evidence. No additional scoring is applied.
      <Link href="/gaps" className="ml-1 font-medium text-primary hover:underline">View scores and original evidence</Link>
    </p>}
  </>;
}

function ProfileSkill({ skill }: { skill: CoreSkillResult }) {
  return <li><Link href="/gaps" className="group flex items-center gap-3 py-3">
    <div className="min-w-0 flex-1"><p className="text-sm font-medium group-hover:text-primary">{SKILL_LABELS[skill.skill_id] ?? skill.skill_id.replaceAll("_", " ")}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{((skill.resume_evidence_strength ?? 0) * 100).toFixed(0)}% résumé evidence · Gap {skill.skill_gap_grade}</p>
    </div><ChevronRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
  </Link></li>;
}
