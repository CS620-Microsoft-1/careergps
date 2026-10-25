"use client";

import Link from "next/link";
import { ChartColumn, Check, CheckCircle2, ChevronRight, Gauge, LoaderCircle, RotateCcw, Sparkles, Target } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { StatCard } from "@/components/common/stat-card";
import { PageHeader } from "@/components/layout/page-header";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FAMILY_LABELS } from "@/lib/confirmed-resume";
import { summarizeSkillGaps } from "@/lib/skill-gap-dashboard";
import { MODULE_LABELS, SKILL_LABELS } from "@/lib/skill-gap-labels";
import { useMarketDemand } from "@/lib/use-market-demand";

export function DashboardWorkspace() {
  const { loaded, snapshot, family, run, submitting, restoring, error, elapsed, analyze } = useSkillGapAnalysis();
  const report = run?.status === "completed" ? run.report : null;
  const summary = report ? summarizeSkillGaps(report) : null;
  const market = useMarketDemand(snapshot ? family : null);
  const sampleSize = summary?.sampleSize ?? (market.data?.job_family === family ? market.data.sample_size : null);
  const busy = submitting || run?.status === "queued" || run?.status === "running";
  const calculating = run?.phase === "checking" || run?.phase === "scoring";
  const failed = run?.status === "failed";
  const role = snapshot ? FAMILY_LABELS[family] : "No target role yet";
  const phaseTitle = calculating ? "Calculating your skill gaps" : run?.phase === "queued" ? "Your analysis is in the queue"
    : submitting || run?.phase === "preparing" ? "Preparing your skill gap analysis" : "Finding evidence in your résumé";

  return <>
    <PageHeader title="Welcome to CareerGPS"
      description="Here's how you'll compare with the job market for your target role."
      actions={<div className="flex items-center gap-2.5 rounded-lg border bg-card py-1.5 pr-1.5 pl-3 text-control">
        <Target aria-hidden className="size-4" /><span className="font-semibold">{role}</span>
        <Button asChild size="sm" variant="secondary" className="bg-background"><Link href={snapshot ? "/onboarding?edit=1" : "/onboarding"}>{snapshot ? "Edit profile" : "Set goal"}</Link></Button>
      </div>} />

    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard label="Career readiness" value="—" detail="Overall readiness is not calculated" />
      <StatCard label="Jobs analyzed" value={sampleSize?.toLocaleString() ?? "—"} detail={sampleSize !== null ? `${role} postings in the demand snapshot` : market.loading ? "Loading your market sample…" : market.error ? "The market snapshot could not be loaded" : "Market sample for your selected direction"} />
      <StatCard label="Skills not evidenced" value={summary ? summary.absent : "—"} detail={summary ? `${summary.scored}/${summary.total} scored · ${summary.pending} need review` : "Available after your first analysis"} />
      <StatCard label="Plan progress" value="—" detail="No action plan created yet">
        <div aria-hidden="true" className="mt-2.5 h-1.5 rounded-full bg-line-soft" />
      </StatCard>
    </div>

    {error && <div role="alert" className="mt-4 rounded-xl border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger">{error}</div>}

    <div className="mt-4 flex flex-wrap items-center gap-4 rounded-xl bg-deep px-5 py-4.5 text-deep-foreground" aria-busy={busy}>
      <span className={`grid size-9 shrink-0 place-items-center rounded-lg bg-white/12 ${busy ? "motion-safe:animate-pulse" : ""}`}>
        {busy ? <LoaderCircle aria-hidden className="size-4.5 motion-safe:animate-spin" /> : report ? <CheckCircle2 aria-hidden className="size-4.5" /> : <Sparkles aria-hidden className="size-4.5" />}
      </span>
      <div className="min-w-0 flex-1 basis-56">
        <div role="status" aria-live="polite" aria-atomic="true">
          <p className="text-xs text-deep-muted">{!loaded ? "Loading your saved profile" : restoring ? "Restoring your saved analysis" : busy ? "Skill gap analysis in progress" : failed ? "Analysis could not finish" : report ? "Your analysis is ready" : "Recommended next step"}</p>
          <p className="text-title font-semibold">{!loaded || restoring ? "Your confirmed résumé and results will appear shortly" : busy ? phaseTitle : failed ? "Your confirmed résumé is safe. You can try again." : report ? "Explore your evidence and priority skill gaps" : snapshot ? `Compare your experience with ${role} skills` : "Upload your résumé to get your first analysis"}</p>
        </div>
        {snapshot && loaded && <p className="mt-1 truncate text-xs text-deep-muted">{snapshot.filename} · Confirmed résumé</p>}
        {failed && run?.error && <p className="mt-1 text-xs text-deep-muted">{run.error}</p>}
      </div>
      {!loaded || restoring ? null : busy ? <span className="text-xs tabular-nums text-deep-muted" aria-live="off">{Math.max(0, Math.floor(elapsed))}s elapsed</span>
        : report ? <Button asChild variant="outline" className="border-0 text-foreground"><Link href="/gaps">View skill gaps <ChevronRight data-icon="inline-end" /></Link></Button>
        : failed ? <Button variant="outline" className="border-0 text-foreground" onClick={() => void analyze(true)}><RotateCcw data-icon="inline-start" />Try again</Button>
        : snapshot ? <Button variant="outline" className="border-0 text-foreground" onClick={() => void analyze(false)}>Analyze skill gaps <ChevronRight data-icon="inline-end" /></Button>
        : <Button asChild variant="outline" className="border-0 text-foreground"><Link href="/onboarding">Get started <ChevronRight data-icon="inline-end" /></Link></Button>}
      {busy && <ol aria-label="Analysis stages" className="grid w-full gap-2 border-t border-white/15 pt-3 text-xs sm:grid-cols-3">
        {[{ label: "Résumé confirmed", done: true, active: false }, { label: "Read skill evidence", done: calculating, active: !calculating }, { label: "Calculate skill gaps", done: false, active: calculating }].map((step, index) => <li key={step.label} aria-current={step.active ? "step" : undefined} className={`flex items-center gap-2 ${step.active || step.done ? "text-deep-foreground" : "text-deep-muted"}`}>
          <span className={`grid size-5 shrink-0 place-items-center rounded-full ${step.done ? "bg-white/20" : "border border-white/25"}`}>{step.done ? <Check className="size-3" aria-hidden="true" /> : <span aria-hidden="true">{index + 1}</span>}</span>
          <span>{step.label}<span className="sr-only">{step.done ? ": completed" : step.active ? ": in progress" : ": waiting"}</span></span>
        </li>)}
      </ol>}
    </div>

    <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
      <Card>
        <CardHeader><CardTitle>Readiness breakdown</CardTitle><CardDescription>{summary ? "Résumé evidence by skill area · not an overall readiness score" : "Your résumé evidence will appear here after analysis"}</CardDescription></CardHeader>
        <CardContent>
          {summary ? <>
            <div className="mb-5 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground"><Legend color="bg-primary" label="Evidence found" /><Legend color="bg-muted-foreground/25" label="Not evidenced" /><Legend color="bg-warning/60" label="Needs review" /></div>
            <div className="grid gap-4">{summary.modules.map((area) => <div key={area.id}>
              <div className="mb-1.5 flex items-center justify-between gap-3 text-xs"><span className="font-medium">{MODULE_LABELS[area.id] ?? area.id.replaceAll("_", " ")}</span><span className="shrink-0 text-muted-foreground">{area.evidenced}/{area.total} evidenced</span></div>
              <div role="img" aria-label={`${area.evidenced} skills with evidence, ${area.absent} not evidenced, ${area.pending} need review`} className="flex h-2 overflow-hidden rounded-full bg-muted"><span className="bg-primary/80" style={{ width: `${area.evidenced / area.total * 100}%` }} /><span className="bg-muted-foreground/25" style={{ width: `${area.absent / area.total * 100}%` }} /><span className="bg-warning/60" style={{ width: `${area.pending / area.total * 100}%` }} /></div>
            </div>)}</div>
            <p className="mt-4 text-xs leading-relaxed text-muted-foreground">Counts show what this résumé demonstrates. Uncertain items stay unscored; they are not treated as missing skills.</p>
          </> : <EmptyState icon={Gauge} title={busy ? "Reading your skill evidence" : "No evidence breakdown yet"} description="Your analysis will show skills with supporting evidence and areas where an example may be missing." />}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Priority skill gaps</CardTitle><CardDescription>{summary ? "Ranked by market demand and résumé evidence gap" : "Your priority skill gaps will appear after analysis"}</CardDescription>
          <CardAction><Button asChild variant="link" className="h-auto p-0"><Link href="/gaps">View all <ChevronRight data-icon="inline-end" /></Link></Button></CardAction>
        </CardHeader>
        <CardContent>{summary?.priorities.length ? <div className="divide-y divide-border">{summary.priorities.map((skill, index) => <Link key={skill.skill_id} href="/gaps" className="group flex items-center gap-3 py-3 first:pt-0 last:pb-0">
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-accent text-xs font-medium text-primary">{index + 1}</span>
          <div className="min-w-0 flex-1"><p className="text-sm font-semibold group-hover:text-primary">{SKILL_LABELS[skill.skill_id] ?? skill.skill_id.replaceAll("_", " ")}</p><p className="mt-0.5 text-xs text-muted-foreground">{(skill.resume_evidence_strength! * 100).toFixed(0)}% résumé evidence</p></div>
          <Badge variant={skill.skill_gap_grade?.startsWith("A") ? "success" : "brand"}>{skill.skill_gap_grade}</Badge><ChevronRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
        </Link>)}</div> : <EmptyState icon={ChartColumn} title={summary ? "No scored gaps to prioritize" : "No gaps identified yet"} description={summary?.pending ? "Some skills need review. Open Skill Gaps to inspect their evidence." : "Your most important skill evidence gaps will be listed here."} />}</CardContent>
      </Card>
    </div>
  </>;
}

function Legend({ color, label }: { color: string; label: string }) {
  return <span className="inline-flex items-center gap-1.5"><span className={`size-2 rounded-full ${color}`} aria-hidden="true" />{label}</span>;
}
