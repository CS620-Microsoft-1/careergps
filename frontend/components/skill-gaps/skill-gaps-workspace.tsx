"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ChartColumn, ChevronDown, Download, LoaderCircle, Play, RotateCcw } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FAMILY_LABELS } from "@/lib/confirmed-resume";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { MODULE_LABELS, SKILL_LABELS } from "@/lib/skill-gap-labels";
import type { CoreAssessment, CoreSkillGapReport, CoreSkillResult, SkillGapRun } from "@/types/api";

const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
const pending = (skill: CoreSkillResult) => skill.resume_evidence_strength === null || skill.skill_gap_grade === null;
const busy = (run: SkillGapRun | null) => run?.status === "queued" || run?.status === "running";

function downloadReport(run: SkillGapRun) {
  const content = { run_id: run.id, filename: run.filename, job_family: run.job_family,
    resume_hash: run.resume_hash, completed_at: run.completed_at, report: run.report };
  const url = URL.createObjectURL(new Blob([JSON.stringify(content, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `careergps-skill-gaps-${run.job_family}.json`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function SkillGapsWorkspace() {
  const { loaded, snapshot, family, run, submitting, restoring, error, elapsed, analyze, changeFamily } = useSkillGapAnalysis();
  const [filter, setFilter] = useState("all");
  useEffect(() => {
    const frame = requestAnimationFrame(() => setFilter("all"));
    return () => cancelAnimationFrame(frame);
  }, [family]);

  const report = run?.report;
  const ranked = useMemo(() => {
    if (!report) return [];
    return [...report.skills].sort((a, b) => {
      if (pending(a) !== pending(b)) return pending(a) ? 1 : -1;
      return (b.priority ?? -1) - (a.priority ?? -1);
    });
  }, [report]);
  const visible = ranked.filter((skill) => filter === "all" ||
    (filter === "pending" ? pending(skill) : !pending(skill) && skill.resume_evidence_strength === 0));
  const scored = report?.skills.filter((skill) => !pending(skill)).length ?? 0;
  const sampleSize = report?.skills[0]?.demand.N;

  if (!loaded) return <p role="status" className="text-muted-foreground">Loading your confirmed résumé…</p>;
  if (!snapshot) return <Card><EmptyState icon={ChartColumn} title="Confirm your résumé first"
    description={error ?? "Upload a résumé, review the extracted information, then confirm your edits. Your skill gaps will use that confirmed version."}
    action={<Button asChild><Link href="/onboarding">Upload and review résumé</Link></Button>} className="py-14" /></Card>;

  return <div className="grid gap-6">
    <Card>
      <CardContent className="grid gap-5 sm:grid-cols-[1fr_auto]">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2"><Badge variant="brand">Local preview</Badge>
            <span className="text-xs text-muted-foreground">Azure analysis · No shared database</span></div>
          <h2 className="truncate font-semibold">{snapshot.filename}</h2>
          <p className="mt-1 text-xs text-muted-foreground">Confirmed {new Date(snapshot.confirmed_at).toLocaleString()}</p>
          <label htmlFor="gap-direction" className="mt-4 block text-xs font-medium">Target direction</label>
          <select id="gap-direction" value={family} onChange={(e) => changeFamily(e.target.value)}
            disabled={submitting || busy(run) || restoring}
            className="mt-1.5 h-10 w-full max-w-72 rounded-lg border border-input bg-background px-3 text-sm focus-visible:ring-2 focus-visible:ring-primary">
            {Object.entries(FAMILY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <div className="flex flex-col items-start justify-center gap-2 sm:items-end">
          <Button onClick={() => void analyze(run?.status === "completed" || run?.status === "failed")} disabled={submitting || busy(run) || restoring}>
            {submitting || busy(run) ? <LoaderCircle className="animate-spin" data-icon="inline-start" /> : run ? <RotateCcw data-icon="inline-start" /> : <Play data-icon="inline-start" />}
            {submitting ? "Starting analysis…" : busy(run) ? "Analyzing…" : run ? "Analyze again" : "Analyze skill gaps"}
          </Button>
          <Button asChild variant="ghost" size="sm"><Link href="/onboarding?edit=1"><ArrowLeft data-icon="inline-start" />Edit confirmed résumé</Link></Button>
          <p className="max-w-60 text-xs text-muted-foreground sm:text-right">Results use your confirmed résumé and the current market-demand snapshot.</p>
        </div>
      </CardContent>
    </Card>

    {error && <div role="alert" className="rounded-xl border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger">{error}</div>}
    {restoring && <p role="status" className="text-sm text-muted-foreground">Loading the saved analysis for this résumé and direction…</p>}
    {run && (busy(run) || run.status === "failed") && <Card><CardContent aria-live="polite" className="flex items-start gap-3">
      {busy(run) && <LoaderCircle className="mt-0.5 size-5 shrink-0 animate-spin text-primary" />}
      <div><p className="font-medium">{run.status === "failed" ? "Analysis could not finish" : run.phase === "queued" ? "Waiting for the local analysis worker" : run.phase === "scoring" || run.phase === "checking" ? "Checking evidence and calculating gaps" : "Reading résumé evidence for your selected direction"}</p>
        <p className="mt-1 text-sm text-muted-foreground">{run.status === "failed" ? run.error ?? "Try again when the local API and Agent are available." : `${Math.floor(elapsed)} seconds elapsed. This can take a minute or more. You can leave this page and return in this tab.`}</p>
        <p className="mt-2 text-xs text-muted-foreground">Model calls for this run: {run.model_calls}. Checking progress does not start another call.</p>
      </div>
    </CardContent></Card>}

    {!run && !restoring && <Card><EmptyState icon={ChartColumn} title="Ready to compare your evidence"
      description={`Analyze your confirmed résumé against the ${FAMILY_LABELS[family]} market snapshot. Choose Analyze skill gaps to compare this direction.`}
      className="py-12" /></Card>}

    {report && run?.status === "completed" && <>
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric title="Skills evaluated" value={`${scored} / ${report.core_skill_count}`} detail="Evidence scored from your confirmed résumé" />
        <Metric title="Needs confirmation" value={String(report.core_skill_count - scored)} detail="Kept unscored; never converted to zero" />
        <Metric title="Market sample" value={sampleSize?.toLocaleString() ?? "—"} detail={`${FAMILY_LABELS[family]} postings in the fixed snapshot`} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="text-lg font-semibold">Your skill evidence gaps</h2>
          <p className="mt-1 text-xs text-muted-foreground">A means a smaller evidence gap. F means not evidenced in this résumé. These are not ability grades or hiring probabilities.</p></div>
        <Button variant="outline" size="sm" onClick={() => downloadReport(run)}><Download data-icon="inline-start" />Download JSON</Button>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <label htmlFor="gap-filter">Show</label><select id="gap-filter" value={filter} onChange={(e) => setFilter(e.target.value)} className="h-8 rounded-md border border-input bg-background px-2 text-foreground">
          <option value="all">All skills</option><option value="pending">Needs confirmation</option><option value="none">Not evidenced</option>
        </select><span>Completed in {run.elapsed_seconds.toFixed(1)}s · Sorted by demand-weighted priority</span>
      </div>
      <Card className="gap-0 overflow-hidden py-0">
        <div aria-hidden className="hidden grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_6rem_5rem_1rem] gap-4 border-b bg-muted/40 px-5 py-3 text-xs font-medium text-muted-foreground md:grid">
          <span>Core skill</span><span>Market demand</span><span>Résumé evidence strength</span><span>Gap grade</span><span>Priority</span><span />
        </div>
        {visible.length ? visible.map((skill) => <SkillEvidenceRow key={skill.skill_id} skill={skill} report={report}
          rank={pending(skill) ? null : ranked.filter((s) => !pending(s)).findIndex((s) => s.skill_id === skill.skill_id) + 1} />)
          : <p className="px-5 py-10 text-center text-sm text-muted-foreground">No skills match this filter.</p>}
      </Card>
      <p className="text-xs leading-relaxed text-muted-foreground">This is an experimental résumé evidence assessment. Review the quotations before acting on a result. Refreshing this page reopens the saved run; it does not rerun the Agent.</p>
    </>}
  </div>;
}

function Metric({ title, value, detail }: { title: string; value: string; detail: string }) {
  return <Card size="sm"><CardContent><p className="text-xs font-medium text-muted-foreground">{title}</p><p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p><p className="mt-1 text-xs text-muted-foreground">{detail}</p></CardContent></Card>;
}

function SkillEvidenceRow({ skill, report, rank }: { skill: CoreSkillResult; report: CoreSkillGapReport; rank: number | null }) {
  const assessment: CoreAssessment = skill.agent_assessment ?? {
    kind: "uncertain", reason: "The source evidence for this item is unavailable and needs review.",
  };
  const isPending = pending(skill);
  const source = report.source_index?.[assessment.operation_id ?? assessment.evidence_id ?? ""];
  const context = source?.activity_context ?? {};
  const activity = [context.name, context.title, context.company, context.organization, context.institution]
    .filter((v): v is string => typeof v === "string" && Boolean(v)).join(" · ");
  const validation = assessment.validation;
  return <details className="group border-b border-border last:border-b-0">
    <summary aria-label={`View evidence for ${SKILL_LABELS[skill.skill_id] ?? skill.skill_id}`} className="grid cursor-pointer list-none gap-3 px-5 py-4 transition-colors hover:bg-muted/25 focus-visible:outline-2 focus-visible:outline-primary md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_6rem_5rem_1rem] md:items-center md:gap-4 [&::-webkit-details-marker]:hidden">
      <div><p className="text-sm font-semibold">{SKILL_LABELS[skill.skill_id] ?? skill.skill_id.replaceAll("_", " ")}</p><p className="mt-1 text-xs text-muted-foreground">{MODULE_LABELS[skill.module_id] ?? "Core skill"}</p></div>
      <div className="text-xs"><span className="text-muted-foreground">Required </span>{percent(skill.demand.required_ratio)}<br /><span className="text-muted-foreground">Preferred </span>{percent(skill.demand.preferred_only_ratio)}</div>
      <div><span className="text-xs text-muted-foreground md:sr-only">Résumé evidence strength: </span><span className="text-sm font-medium">{skill.resume_evidence_strength === null ? "—" : percent(skill.resume_evidence_strength)}</span>
        {skill.resume_evidence_strength !== null && <div className="mt-1.5 h-1.5 max-w-32 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary/65" style={{ width: percent(skill.resume_evidence_strength) }} /></div>}</div>
      <div><span className="text-xs text-muted-foreground md:sr-only">Gap grade: </span><Badge variant={isPending ? "warning" : skill.skill_gap_grade?.startsWith("A") ? "success" : skill.skill_gap_grade === "F" ? "outline" : "brand"}>{isPending ? "Needs review" : skill.skill_gap_grade}</Badge></div>
      <span className="text-xs text-muted-foreground">{rank === null ? "Unscored" : `#${rank}`}</span><ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
    </summary>
    <div className="grid gap-5 border-t border-border bg-muted/15 px-5 py-5 md:grid-cols-[1.6fr_1fr]">
      <div className="grid gap-4">
        <div><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Résumé evidence</p>{activity && <p className="mt-1 text-sm">{activity}</p>}</div>
        {isPending && <div className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm">
          <p className="font-medium">Needs confirmation — no score assigned</p>
          <p className="mt-1 text-xs">{assessment.reason ?? (skill.local_reference_check.errors.some((e) => e.code === "quote_not_in_original") ? "A quotation could not be matched exactly to the confirmed résumé." : "The source or relevance of this evidence needs review.")}</p>
        </div>}
        {assessment.kind === "absent" ? <p className="text-sm text-muted-foreground">No positive evidence was identified for this skill in this résumé. This does not mean you lack the skill.</p>
          : assessment.kind === "knowledge" ? <EvidenceBlock label="Listed or course knowledge" quote={source?.text} />
          : <><EvidenceBlock label="Operation" quote={assessment.capability?.quote ?? source?.text} />
            <EvidenceBlock label="Method" quote={assessment.method?.proof?.quote} />
            <EvidenceBlock label="Check" quote={validation?.check?.quote} />
            <EvidenceBlock label="Reported finding" quote={validation?.finding?.quote} />
            {validation?.reference && <EvidenceBlock label="Comparison reference" quote={validation.reference.quote} />}</>}
        {source?.text && <details className="rounded-lg border border-border p-3"><summary className="cursor-pointer text-xs font-medium">View full original résumé statement</summary><blockquote className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink-2">{source.text}</blockquote></details>}
      </div>
      <div className="h-fit rounded-lg border border-border bg-background p-4 text-xs">
        <h4 className="font-semibold">Market-demand detail</h4>
        <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-3 gap-y-2">
          <dt className="text-muted-foreground">Required</dt><dd>{percent(skill.demand.required_ratio)} · {skill.demand.required_job_count} postings</dd>
          <dt className="text-muted-foreground">Preferred only</dt><dd>{percent(skill.demand.preferred_only_ratio)} · {skill.demand.preferred_only_job_count} postings</dd>
          <dt className="text-muted-foreground">Level unspecified</dt><dd>{percent(skill.demand.unspecified_ratio)} · {skill.demand.unspecified_job_count} postings</dd>
          <dt className="text-muted-foreground">Sample size</dt><dd>{skill.demand.N.toLocaleString()}</dd>
          <dt className="text-muted-foreground">Evidence gap</dt><dd>{skill.skill_gap === null ? "—" : percent(skill.skill_gap)}</dd>
          <dt className="text-muted-foreground">Weighted priority</dt><dd>{skill.priority === null ? "—" : skill.priority.toFixed(3)}</dd>
        </dl><p className="mt-3 leading-relaxed text-muted-foreground">Demand comes from the fixed local snapshot. The Agent does not calculate these ratios.</p>
      </div>
    </div>
  </details>;
}

function EvidenceBlock({ label, quote }: { label: string; quote?: string | null }) {
  return <div><p className="text-xs font-semibold text-muted-foreground">{label}</p>
    {quote ? <blockquote className="mt-1 border-l-2 border-primary/25 pl-3 text-sm leading-relaxed">{quote}</blockquote>
      : <p className="mt-1 text-xs text-muted-foreground">Not reported or not selected.</p>}</div>;
}
