"use client";

import Link from "next/link";
import { FileText, LoaderCircle, Plus, RotateCcw, TrendingUp, Upload } from "lucide-react";

import { AnalysisGate, ROLE_NAMES, RoutePageHeader, SourceNote, skillLabel } from "@/components/career/route-parts";
import { ADD_DESTINATION_HREF, FAMILIES, useDestinationRuns } from "@/components/destinations/use-destination-runs";
import { useAccount } from "@/components/layout/account-provider";
import { useSwitchRoute } from "@/components/layout/use-switch-route";
import { usePlan } from "@/components/plan/plan-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { isScored, percent, rankGaps, STRONG_STRENGTH } from "@/lib/career";
import { useMarketDemand } from "@/lib/use-market-demand";
import { cn } from "@/lib/utils";
import type { CoreSkillGapReport, JobFamily, MarketDemandSnapshot } from "@/types/api";

/** Common titles for each role, to search job boards with. */
const SEARCH_TITLES: Record<JobFamily, string[]> = {
  data_analyst: ["Junior data analyst", "Reporting analyst", "Business intelligence analyst", "Analytics intern"],
  software_engineer: ["Software engineer I", "New grad software engineer", "Backend engineer", "Software engineering intern"],
  ai_engineer: ["Machine learning engineer", "AI engineer", "Applied scientist", "ML engineering intern"],
};

export function DestinationsView() {
  const { families: explored, resumes, runs } = useDestinationRuns();
  const { snapshot, run } = useSkillGapAnalysis();
  const { user } = useAccount();
  const { family, locked, switchTo } = useSwitchRoute();
  const market = useMarketDemand(snapshot ? family : null);
  const report = run?.status === "completed" ? run.report : null;
  const role = ROLE_NAMES[family];

  return <>
    <RoutePageHeader title="Your destinations"
      description="Focus on a few. Pick one to see what its job market is asking for right now." />

    <div className="grid gap-4 md:grid-cols-3">
      {explored.map((key) => {
        const { status, run: latest } = runs[key];
        const done = latest?.status === "completed" && latest.report;
        const value = done ? latest.match?.score ?? null : null;
        const gaps = done ? rankGaps(latest.report!).length : null;
        const selected = key === family;
        return (
          <button key={key} type="button" aria-pressed={selected} disabled={locked && !selected} onClick={() => void switchTo(key)}
            className={cn("grid gap-4 rounded-2xl border border-border bg-card p-6 text-left shadow-card transition-colors hover:bg-background disabled:opacity-60",
              selected && "border-2 border-foreground")}>
            <span className="flex items-baseline justify-between gap-3">
              <span className="text-title">{ROLE_NAMES[key]}</span>
              <span className="font-mono text-xl">{value === null ? "—" : percent(value)}</span>
            </span>
            <span className="-mt-3 truncate text-sm text-muted-foreground">
              {resumes[key]?.original_filename ?? (selected ? snapshot?.filename : undefined) ?? "Your résumé"}{user?.preferred_location ? ` · ${user.preferred_location}` : ""}
            </span>
            <span aria-hidden className="h-2 rounded-full bg-sunken">
              <span className="block h-full rounded-full bg-foreground" style={{ width: `${(value ?? 0) * 100}%` }} />
            </span>
            <span className="flex justify-between gap-3 text-sm">
              <span className="text-muted-foreground">
                {status === "loading" ? "Loading…" : gaps !== null ? `${gaps} gaps` : latest && latest.status !== "failed" ? "Analyzing…" : "Not analyzed yet"}
              </span>
              <b>{selected ? "Selected" : "Select"}</b>
            </span>
          </button>
        );
      })}
      {snapshot && explored.length < FAMILIES.length && (
        <Link href={ADD_DESTINATION_HREF}
          className="grid min-h-40 place-content-center justify-items-center gap-2 rounded-2xl border border-dashed border-line-strong p-6 text-center transition-colors hover:bg-card">
          <span aria-hidden className="grid size-10 place-items-center rounded-full bg-accent"><Plus className="size-5" /></span>
          <span className="text-title">Add a destination</span>
          <span className="text-sm text-muted-foreground">Compare your résumé with another role</span>
        </Link>
      )}
    </div>

    <div className="mt-12 flex flex-wrap items-end justify-between gap-3">
      <h2 className="text-page-title">{role} market</h2>
      {market.data && <SourceNote>Based on {market.data.sample_size.toLocaleString()} job postings{market.data.posting_window ? ` · ${market.data.posting_window}` : ""}</SourceNote>}
    </div>

    {snapshot && <div className="mt-5 flex flex-wrap items-center gap-3 rounded-2xl bg-sunken px-5 py-3.5">
      <FileText aria-hidden className="size-4.5" />
      <p className="min-w-0 flex-1">{role} is matched against <b>{snapshot.filename}</b></p>
      <Button asChild size="sm" variant="outline"><Link href="/onboarding"><Upload data-icon="inline-start" />Upload a new résumé for this role</Link></Button>
    </div>}

    {market.loading ? <p role="status" className="mt-6 flex items-center gap-2 text-muted-foreground"><LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />Loading the market…</p>
      : market.error ? <div role="alert" className="mt-6 flex flex-wrap items-center gap-3 rounded-2xl bg-danger-soft p-5">
        <p className="flex-1">{market.error}</p>
        <Button size="sm" variant="raised" onClick={market.reload}><RotateCcw data-icon="inline-start" />Try again</Button>
      </div>
      : market.data && <Market data={market.data} report={report} family={family} />}

    {!report && snapshot && <div className="mt-6"><AnalysisGate /></div>}
  </>;
}

function Market({ data, report, family }: { data: MarketDemandSnapshot; report: CoreSkillGapReport | null; family: JobFamily }) {
  const plan = usePlan();
  const share = (s: MarketDemandSnapshot["skills"][number]) => s.required_ratio + s.preferred_only_ratio;
  const top = [...data.skills].sort((a, b) => share(b) - share(a) || a.skill_id.localeCompare(b.skill_id)).slice(0, 8);
  const results = new Map(report?.skills.map((skill) => [skill.skill_id, skill]));
  const biggest = report ? rankGaps(report)[0] : undefined;
  const planned = biggest && plan.items.some((item) => plan.resources.find((r) => r.id === item.resource_id)?.skills.includes(biggest.skill_id));

  return <>
    <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Stat value={data.sample_size.toLocaleString()} label="postings analyzed" />
      <Stat value={String(data.core_skill_count)} label="core skills tracked" />
      <Stat value={data.company_coverage === null ? "—" : data.company_coverage.toLocaleString()} label="companies covered" />
      <Stat value={new Date(data.snapshot_generated_at).toLocaleDateString(undefined, { month: "short", year: "numeric", timeZone: "UTC" })} label="snapshot date" />
    </div>

    <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <section aria-labelledby="asked" className="rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8">
        <div className="flex items-baseline justify-between gap-3">
          <h3 id="asked" className="text-title">Most-asked skills</h3>
          <Link href="/gaps" className="text-sm font-bold hover:underline">See your gaps</Link>
        </div>
        <ul className="mt-5 grid gap-4">
          {top.map((skill) => {
            const result = results.get(skill.skill_id);
            const tag = !result ? null : !isScored(result) ? "review"
              : result.resume_evidence_strength! >= STRONG_STRENGTH ? "strength" : "gap";
            return (
              <li key={skill.skill_id} className="grid items-center gap-x-4 gap-y-1.5 sm:grid-cols-[minmax(0,13rem)_6.5rem_minmax(0,1fr)_3rem]">
                <span className="font-bold">{skillLabel(skill.skill_id)}</span>
                <span>{tag && <Badge variant={tag === "gap" ? "danger" : tag === "strength" ? "success" : "warning"}>{tag}</Badge>}</span>
                <span aria-hidden className="h-2 rounded-full bg-sunken">
                  <span className="block h-full rounded-full bg-foreground" style={{ width: `${share(skill) * 100}%` }} />
                </span>
                <span className="font-mono text-sm text-muted-foreground sm:text-right">{percent(share(skill))}</span>
              </li>
            );
          })}
        </ul>
        <p className="mt-5 text-sm text-muted-foreground">Bars show the share of postings that require or prefer each skill.</p>
        <details className="mt-4 border-t border-border pt-4 text-sm text-muted-foreground">
          <summary className="cursor-pointer font-bold text-foreground">About this data</summary>
          <p className="mt-2">{data.source_description}</p>
          {data.coverage_limitations.length > 0 && <ul className="mt-2 list-disc pl-5">{data.coverage_limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
        </details>
      </section>

      <aside className="grid gap-5">
        {biggest && <section className="flex gap-3 rounded-2xl bg-warning-soft p-5">
          <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-full bg-card"><TrendingUp className="size-4.5" /></span>
          <div>
            <p className="font-bold">Biggest gap: {skillLabel(biggest.skill_id)}</p>
            <p className="mt-1 text-sm/6">
              {percent(biggest.demand.required_ratio + biggest.demand.preferred_only_ratio)} of postings ask for it.{" "}
              {planned ? "It’s already in your action plan." : <Link href={`/resources?gap=${biggest.skill_id}`} className="font-bold underline">Find ways to close it</Link>}
            </p>
          </div>
        </section>}
        <section aria-labelledby="titles" className="rounded-2xl border border-border bg-card p-6 shadow-card">
          <h3 id="titles" className="text-title">Titles to search for</h3>
          <ul className="mt-3 flex flex-wrap gap-2">
            {SEARCH_TITLES[family].map((title) => <li key={title} className="rounded-full bg-sunken px-3 py-1 text-sm font-semibold">{title}</li>)}
          </ul>
        </section>
        <section className="rounded-2xl bg-sunken p-6">
          <h3 className="text-title">One résumé per destination</h3>
          <p className="mt-2 text-sm/6 text-muted-foreground">Each role is matched against its own résumé. Uploading a new version for one role leaves the others as they are.</p>
        </section>
      </aside>
    </div>
  </>;
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card px-5 py-4 shadow-card">
      <p className="font-mono text-2xl font-medium">{value}</p>
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}
