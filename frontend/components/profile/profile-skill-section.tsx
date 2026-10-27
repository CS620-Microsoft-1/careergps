"use client";

import Link from "next/link";
import { ChevronRight, LoaderCircle } from "lucide-react";

import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Card, CardContent } from "@/components/ui/card";
import { groupProfileSkills } from "@/lib/profile-skills";
import { FAMILY_LABELS } from "@/lib/skill-gap-profile";
import { SKILL_LABELS } from "@/lib/skill-gap-labels";
import type { CoreSkillResult } from "@/types/api";

const COLUMNS = [
  { key: "strong", title: "Strong", dot: "bg-success" },
  { key: "some", title: "Some experience", dot: "bg-warning-fill" },
  { key: "absent", title: "Not yet demonstrated", dot: "bg-danger" },
] as const;

/** Add evidence groups to the account-backed profile without replacing its identity or résumé sections. */
export function ProfileSkillSection() {
  const { loaded, snapshot, family, run, submitting, restoring, error } = useSkillGapAnalysis();
  const report = run?.status === "completed" && run.report?.job_family === family ? run.report : null;
  const groups = groupProfileSkills(report);
  const busy = submitting || run?.status === "queued" || run?.status === "running";
  return <>
    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg bg-accent px-3.5 py-2.5 text-control text-accent-foreground">
      {(busy || restoring || !loaded) && <LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />}
      <p role="status" className="min-w-0 flex-1">{!loaded || restoring ? "Loading your saved skill analysis…"
        : busy ? "Analyzing your confirmed résumé…"
        : report ? `Résumé evidence for ${FAMILY_LABELS[family]}. These groups describe evidence, not ability.`
        : "Skill ratings will appear after you analyze your confirmed résumé."}</p>
      {snapshot && <Link href="/gaps" className="inline-flex items-center gap-1 text-xs font-semibold hover:underline">View skill gaps<ChevronRight className="size-3.5" /></Link>}
    </div>
    {(error || run?.status === "failed") && <p role="alert" className="mb-4 text-sm text-destructive">{error ?? run?.error}</p>}
    {groups.pending.length > 0 && <p className="mb-4 text-sm text-muted-foreground">{groups.pending.length} skills need review and have no assigned score. They are separate from missing evidence.</p>}
    <div className="grid items-start gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {COLUMNS.map(({ key, title, dot }) => <Card key={key} size="sm"><CardContent>
        <h3 className="flex items-center gap-2 text-sm"><span aria-hidden className={`size-2 rounded-full ${dot}`} />{title}
          <span className="ml-auto font-normal text-muted-foreground">{report ? groups[key].length : "—"}</span></h3>
        {report && groups[key].length > 0 ? <ul className="mt-3 divide-y divide-line-soft border-t border-line-soft">
          {groups[key].map((skill) => <ProfileSkill key={skill.skill_id} skill={skill} />)}
        </ul> : <p className="mt-3 border-t border-line-soft pt-3 text-control text-muted-foreground">{report
          ? "No skills in this evidence band yet." : "Skill ratings will appear here once the gap analysis is ready."}</p>}
      </CardContent></Card>)}
    </div>
  </>;
}

function ProfileSkill({ skill }: { skill: CoreSkillResult }) {
  return <li><Link href="/gaps" className="group flex items-center gap-3 py-3">
    <div className="min-w-0 flex-1"><p className="text-sm font-medium group-hover:text-primary">{SKILL_LABELS[skill.skill_id] ?? skill.skill_id.replaceAll("_", " ")}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{((skill.resume_evidence_strength ?? 0) * 100).toFixed(0)}% résumé evidence · Gap {skill.skill_gap_grade}</p></div>
    <ChevronRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
  </Link></li>;
}
