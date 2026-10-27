import { percent } from "@/lib/career";
import type { CoreAssessment, CoreSkillGapReport, CoreSkillResult } from "@/types/api";

/** The résumé quotes behind one skill's rating, and the demand numbers it was weighted by. */
export function SkillEvidence({ skill, report }: { skill: CoreSkillResult; report: CoreSkillGapReport }) {
  const assessment: CoreAssessment = skill.agent_assessment ?? {
    kind: "uncertain", reason: "The source evidence for this item is unavailable and needs review.",
  };
  const pending = skill.resume_evidence_strength === null || skill.skill_gap_grade === null;
  const source = report.source_index?.[assessment.operation_id ?? assessment.evidence_id ?? ""];
  const context = source?.activity_context ?? {};
  const activity = [context.name, context.title, context.company, context.organization, context.institution]
    .filter((v): v is string => typeof v === "string" && Boolean(v)).join(" · ");
  const validation = assessment.validation;
  return (
    // Side by side only when the card itself is wide; in the narrow review column it stacks.
    <div className="@container">
    <div className="grid gap-5 @xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <div className="grid min-w-0 content-start gap-4">
        {activity && <p className="text-sm"><span className="eyebrow mr-2">From</span>{activity}</p>}
        {pending && <div className="rounded-lg bg-warning-soft p-3 text-sm">
          <p className="font-bold">Needs your review: no score yet</p>
          <p className="mt-1">{assessment.reason ?? (skill.local_reference_check.errors.some((e) => e.code === "quote_not_in_original")
            ? "A quotation could not be matched exactly to your confirmed résumé."
            : "We couldn’t tell whether this evidence is yours or relevant.")}</p>
        </div>}
        {assessment.kind === "absent" ? <p className="text-sm text-muted-foreground">We didn’t find this skill in your résumé. That doesn’t mean you lack it; it means a recruiter can’t see it yet.</p>
          : assessment.kind === "knowledge" ? <Quote label="Listed or coursework" quote={source?.text} />
          : <>
            <Quote label="What you did" quote={assessment.capability?.quote ?? source?.text} />
            <Quote label="How" quote={assessment.method?.proof?.quote} />
            <Quote label="How you checked it" quote={validation?.check?.quote} />
            <Quote label="Result" quote={validation?.finding?.quote} />
            {validation?.reference && <Quote label="Compared with" quote={validation.reference.quote} />}
          </>}
        {source?.text && <details className="rounded-lg border border-border p-3">
          <summary className="cursor-pointer text-sm font-bold">Full résumé line</summary>
          <blockquote className="mt-2 text-sm/6 whitespace-pre-wrap text-muted-foreground">{source.text}</blockquote>
        </details>}
      </div>
      <dl className="grid h-fit min-w-0 grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1.5 rounded-lg bg-sunken p-4 text-sm [&_dd]:text-right [&_dd]:font-mono [&_dd]:whitespace-nowrap">
        <dt className="text-muted-foreground">Required in</dt><dd>{percent(skill.demand.required_ratio)} · {skill.demand.required_job_count}</dd>
        <dt className="text-muted-foreground">Preferred in</dt><dd>{percent(skill.demand.preferred_only_ratio)} · {skill.demand.preferred_only_job_count}</dd>
        <dt className="text-muted-foreground">Postings</dt><dd>{skill.demand.N.toLocaleString()}</dd>
        <dt className="text-muted-foreground">Evidence</dt><dd>{skill.resume_evidence_strength === null ? "—" : percent(skill.resume_evidence_strength)}</dd>
        <dt className="text-muted-foreground">Gap grade</dt><dd>{skill.skill_gap_grade ?? "—"}</dd>
      </dl>
    </div>
    </div>
  );
}

function Quote({ label, quote }: { label: string; quote?: string | null }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      {quote ? <blockquote className="mt-1 border-l-2 border-foreground pl-3 text-sm/6">{quote}</blockquote>
        : <p className="mt-1 text-sm text-muted-foreground">Not in your résumé yet.</p>}
    </div>
  );
}
