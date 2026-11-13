"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BookmarkCheck, Check, ChevronDown, ChevronRight, ExternalLink, Layers, LoaderCircle } from "lucide-react";

import {
  RESOURCE_TYPES,
  RESOURCE_TYPE_ORDER,
  ResourceIcon,
  RoutePageHeader,
  SaveButton,
  skillLabel,
} from "@/components/career/route-parts";
import { useAccount } from "@/components/layout/account-provider";
import { usePlan } from "@/components/plan/plan-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getCertificationPicks, getProjectPicks } from "@/lib/api/resources";
import { rankGaps } from "@/lib/career";
import { cn } from "@/lib/utils";
import type { JobFamily, Resource, ResourceType } from "@/types/api";

export function ResourcesView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { run, snapshot, loaded, family, error } = useSkillGapAnalysis();
  const { user } = useAccount();
  const plan = usePlan();
  const [type, setType] = useState<ResourceType | "all">("all");

  const report = run?.status === "completed" ? run.report : null;
  const { byId: picks, projectsPending } = usePicks(family, report ? run!.id : null);
  const pickOrder = [...picks.keys()];
  const gaps = report ? rankGaps(report).map((gap) => gap.skill_id) : [];
  const requestedGap = params.get("gap");
  const gap = requestedGap && plan.resources.some((r) => r.skills.includes(requestedGap)) ? requestedGap : null;
  // Ranked order, so choosing a gap never moves it. A gap linked from elsewhere that isn't in the
  // top six goes at the end.
  const topGaps = gaps.slice(0, 6);
  const gapOptions = gap && !topGaps.includes(gap) ? [...topGaps, gap] : topGaps;
  const setGap = (value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set("gap", value); else next.delete("gap");
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const byGap = gap ? plan.resources.filter((r) => r.skills.includes(gap)) : plan.resources;
  const visible = type === "all" ? byGap : byGap.filter((r) => r.type === type);
  const school = plan.resources.find((r) => r.school)?.school ?? null;

  return <>
    <RoutePageHeader title="Ways to close your gaps"
      description="Save the ones you’ll actually do. We’ll put them in your action plan in the best order."
      aside={<div className="flex items-center gap-3 rounded-full border border-border bg-card py-1.5 pr-1.5 pl-4 shadow-card">
        <BookmarkCheck aria-hidden className="size-4.5 text-success" />
        <span className="font-bold">{plan.items.length} saved</span>
        <Button asChild variant="outline" size="sm"><Link href="/plan">View action plan<ChevronRight data-icon="inline-end" /></Link></Button>
      </div>} />

    {!loaded || plan.status === "loading" ? <p role="status" className="flex items-center gap-2 text-muted-foreground"><LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />Loading resources…</p>
      // No snapshot because the profile couldn't be loaded, not because there's no résumé.
      : !snapshot && error ? <p role="alert" className="rounded-2xl bg-danger-soft p-6">{error}</p>
      : !snapshot ? <p className="rounded-2xl border border-border bg-card p-6">Upload your résumé first, then we’ll match resources to your gaps. <Link href="/onboarding" className="font-bold underline">Upload résumé</Link></p>
      : plan.status === "error" ? <p role="alert" className="rounded-2xl bg-danger-soft p-6">{plan.error}</p>
      : <>
        {gap && <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl bg-sunken px-5 py-3.5">
          <Layers aria-hidden className="size-4.5" />
          <p className="min-w-0 flex-1">Showing resources that close <b>{skillLabel(gap)}</b></p>
          <Button size="sm" variant="raised" onClick={() => setGap(null)}>Show all gaps</Button>
        </div>}
        {plan.actionError && <p role="alert" className="mb-4 text-sm text-destructive">{plan.actionError}</p>}

        <div className="grid items-start gap-8 lg:grid-cols-[15rem_minmax(0,1fr)]">
          <aside className="grid gap-5">
            <FilterGroup title="Gap" options={[
              { key: null, label: "All gaps", count: plan.resources.length },
              ...gapOptions.map((skill) => ({ key: skill, label: skillLabel(skill),
                count: plan.resources.filter((r) => r.skills.includes(skill)).length })),
            ]} value={gap} onChange={setGap} />
            <FilterGroup title="Type" options={[
              { key: "all" as const, label: "All types", count: byGap.length },
              ...RESOURCE_TYPE_ORDER.map((key) => ({ key, label: typeHeading(key, school),
                count: byGap.filter((r) => r.type === key).length })).filter((o) => o.count > 0),
            ]} value={type} onChange={(value) => setType(value ?? "all")} />
            <div className={cn("rounded-2xl p-5", school ? "bg-success-soft" : "bg-sunken")}>
              <p className="flex items-center gap-2 font-bold">{school && <Check aria-hidden className="size-4.5" />}
                {school ? `${shortSchool(school)} resources` : "Campus resources"}</p>
              <p className="mt-1 text-sm/6">
                {school ? `Your profile lists ${user?.university ?? school}, so we include its student orgs and courses.`
                  : "We have campus courses and clubs for a few schools. Your school isn’t one of them yet."}
              </p>
            </div>
          </aside>

          <div className="grid gap-10">
            {RESOURCE_TYPE_ORDER.map((key) => {
              // Recommended ones first, in the order they were picked; the rest keep catalog order.
              const group = visible.filter((r) => r.type === key)
                .sort((a, b) => rank(pickOrder, a.id) - rank(pickOrder, b.id));
              if (!group.length) return null;
              // Projects: the agent's top picks up front, every other project under "More projects".
              const split = key === "project" ? splitProjects(group, picks, gaps, projectsPending) : null;
              const shown = split ? split.top : group;
              return (
                <section key={key} aria-labelledby={`type-${key}`}>
                  <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <h2 id={`type-${key}`} className="text-section">{typeHeading(key, school)}</h2>
                    <span className="font-mono text-sm">{group.length}</span>
                    <span className="text-sm text-muted-foreground">{RESOURCE_TYPES[key].blurb}</span>
                  </div>
                  {split && projectsPending && !split.top.length && (
                    <p role="status" className="flex items-center gap-2 rounded-2xl border border-border bg-card p-5 text-muted-foreground">
                      <LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />Picking your top {TOP_PROJECTS} projects…
                    </p>
                  )}
                  {shown.length > 0 && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {shown.map((resource) => <ResourceCard key={resource.id} resource={resource} gaps={gaps} pick={picks.get(resource.id)} />)}
                  </div>}
                  {split && split.more.length > 0 && <MoreProjects resources={split.more} gaps={gaps} picks={picks} />}
                </section>
              );
            })}
            {visible.length === 0 && <p className="text-muted-foreground">No resources match these filters.</p>}
          </div>
        </div>
      </>}
  </>;
}

/** pick: undefined when not recommended, otherwise the reason (null when the rule ranking chose it). */
function ResourceCard({ resource, gaps, pick }: { resource: Resource; gaps: string[]; pick?: string | null }) {
  // Only skills that are gaps, in gap order; strengths it also practices aren't "closed".
  const closes = resource.skills.filter((skill) => gaps.includes(skill))
    .sort((a, b) => rank(gaps, a) - rank(gaps, b)).slice(0, 2);
  return (
    <article className="flex flex-col rounded-2xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center gap-3">
        <ResourceIcon type={resource.type} className="bg-sunken" />
        <p className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{resource.provider}</p>
        {pick !== undefined && <Badge variant="brand">Recommended</Badge>}
      </div>
      <h3 className="mt-4 text-title">{resource.title}</h3>
      <p className="mt-1 font-mono text-[0.8125rem] text-muted-foreground">{resource.meta}</p>
      {resource.description && <p className="mt-3 text-sm/6 text-muted-foreground">{resource.description}</p>}
      {pick && <p className="mt-3 rounded-lg bg-accent px-3 py-2 text-sm/6">{pick}</p>}
      {closes.length > 0 && <p className="mt-auto pt-4 text-sm">Closes: <b>{closes.map(skillLabel).join(", ")}</b></p>}
      <div className={cn("flex items-center gap-2", closes.length ? "mt-4" : "mt-auto pt-4")}>
        <SaveButton resourceId={resource.id} />
        {resource.url && <Button asChild size="icon-sm" variant="ghost">
          <a href={resource.url} target="_blank" rel="noreferrer" aria-label={`Open ${resource.title} in a new tab`}><ExternalLink /></a>
        </Button>}
      </div>
    </article>
  );
}

function FilterGroup<K extends string | null>({ title, options, value, onChange }: {
  title: string; options: { key: K; label: string; count: number }[]; value: K; onChange: (key: K) => void;
}) {
  return (
    <fieldset className="rounded-2xl border border-border bg-card p-4 shadow-card">
      <legend className="sr-only">{title}</legend>
      <p aria-hidden className="eyebrow mb-2 px-1">{title}</p>
      <div className="grid gap-1">
        {options.map((option) => (
          <button key={option.key ?? "all"} type="button" aria-pressed={option.key === value} onClick={() => onChange(option.key)}
            className={cn("flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-background",
              option.key === value && "bg-accent font-bold hover:bg-accent")}>
            <span>{option.label}</span><span className="font-mono text-sm">{option.count}</span>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

/** Every project not on top, in a collapsed list whose cards are only built once it's opened. */
function MoreProjects({ resources, gaps, picks }: { resources: Resource[]; gaps: string[]; picks: Map<string, string | null> }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="group mt-4 rounded-2xl border border-border bg-card shadow-card"
      onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-2xl px-5 py-4 font-bold hover:bg-background [&::-webkit-details-marker]:hidden">
        <span>More projects <span className="ml-1 font-mono text-sm font-normal text-muted-foreground">{resources.length}</span></span>
        <ChevronDown aria-hidden className="size-4.5 transition-transform group-open:rotate-180" />
      </summary>
      {open && (
        <div className="grid gap-4 border-t border-border p-4 sm:grid-cols-2 xl:grid-cols-3">
          {resources.map((resource) => <ResourceCard key={resource.id} resource={resource} gaps={gaps} pick={picks.get(resource.id)} />)}
        </div>
      )}
    </details>
  );
}

const NO_PICKS = new Map<string, string | null>();
/** How many projects show before "More projects"; the agent recommends at most this many. */
const TOP_PROJECTS = 3;

/**
 * The agent's project picks (in pick order) as the top projects, the rest under "More projects",
 * ordered by how many of the student's gaps they close. Without picks (no analysis yet, the agent
 * failed, or a gap filter hides them) the projects that close the most gaps go on top instead;
 * while picks are still loading, nothing does, so the top doesn't jump when they arrive.
 */
function splitProjects(projects: Resource[], picks: Map<string, string | null>, gaps: string[], pending: boolean) {
  const closed = (resource: Resource) => resource.skills.filter((skill) => gaps.includes(skill)).length;
  const byCoverage = (list: Resource[]) => list
    .map((resource, index) => ({ resource, index }))
    .sort((a, b) => closed(b.resource) - closed(a.resource) || a.index - b.index)
    .map(({ resource }) => resource);
  const picked = projects.filter((resource) => picks.has(resource.id));
  const top = picked.length ? picked.slice(0, TOP_PROJECTS) : pending ? [] : byCoverage(projects).slice(0, TOP_PROJECTS);
  const onTop = new Set(top.map((resource) => resource.id));
  return { top, more: byCoverage(projects.filter((resource) => !onTop.has(resource.id))) };
}

/**
 * Certification and project picks for the role's analysis: resource id → reason, in pick order.
 * projectsPending is true until the project picks for this analysis have come back (or failed).
 */
function usePicks(family: JobFamily, runId: string | null) {
  type Loaded = { key: string; byId: Map<string, string | null> };
  const [certifications, setCertifications] = useState<Loaded | null>(null);
  const [projects, setProjects] = useState<Loaded | null>(null);
  const key = `${family}:${runId}`;
  useEffect(() => {
    if (!runId) return;
    let active = true;
    // Each list loads on its own, so slow certification picks don't hold up the project picks.
    // Either can fail on its own (it then counts as loaded with no picks); the catalog still shows everything.
    const load = (request: Promise<Map<string, string | null>>, set: (loaded: Loaded) => void) => {
      void request.then(
        (byId) => { if (active) set({ key, byId }); },
        () => { if (active) set({ key, byId: new Map() }); },
      );
    };
    load(getCertificationPicks(family).then((response) =>
      new Map(response.recommendations.map((pick) => [pick.certification_id, pick.reason]))), setCertifications);
    // A project pick's reason only restates the skills the card already lists under Closes.
    load(getProjectPicks(runId).then((response) =>
      new Map(response.recommendations.map((pick) => [pick.project_id, null]))), setProjects);
    return () => { active = false; };
  }, [family, runId, key]);
  const certificationPicks = certifications?.key === key ? certifications.byId : null;
  const projectPicks = projects?.key === key ? projects.byId : null;
  const byId = useMemo(
    () => (certificationPicks || projectPicks ? new Map([...(certificationPicks ?? []), ...(projectPicks ?? [])]) : NO_PICKS),
    [certificationPicks, projectPicks],
  );
  return { byId, projectsPending: runId !== null && projectPicks === null };
}

const rank = (order: string[], key: string) => {
  const index = order.indexOf(key);
  return index < 0 ? Number.POSITIVE_INFINITY : index;
};

function typeHeading(type: ResourceType, school: string | null) {
  return type === "school_course" && school ? `Courses at ${shortSchool(school)}` : RESOURCE_TYPES[type].plural;
}

/** "University of Wisconsin–Madison" → "UW–Madison"; other names stay as they are. */
function shortSchool(name: string) {
  return name.replace(/^University of Wisconsin[–-]/, "UW–");
}
