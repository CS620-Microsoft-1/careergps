"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import NumberFlow from "@number-flow/react";
import { BookmarkCheck, Check, ChevronDown, ChevronRight, ExternalLink, Layers, LoaderCircle } from "lucide-react";

import {
  RESOURCE_TYPES,
  RESOURCE_TYPE_ORDER,
  ResourceIcon,
  RoutePageHeader,
  SaveButton,
  numberTiming,
  skillLabel,
} from "@/components/career/route-parts";
import { useAccount } from "@/components/layout/account-provider";
import { usePlan } from "@/components/plan/plan-provider";
import { useTakenCourses } from "@/components/plan/taken-courses-provider";
import { ResumeCourseMatches, TakenButton, TakenUndo } from "@/components/resources/taken-courses";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getCertificationPicks, getProjectPicks } from "@/lib/api/resources";
import { TOP_PICKS, rankGaps, splitTopPicks, withoutTaken } from "@/lib/career";
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
  const { taken } = useTakenCourses();
  const [showTaken, setShowTaken] = useState(false);
  const [justTaken, setJustTaken] = useState<Resource | null>(null);
  // Courses the student has taken stay out of the lists unless they ask to see them.
  const listed = withoutTaken(plan.resources, taken);

  const report = run?.status === "completed" ? run.report : null;
  const { picks, pending } = usePicks(family, report ? run!.id : null);
  const pickOrder = [...picks];
  const gaps = report ? rankGaps(report).map((gap) => gap.skill_id) : [];
  const requestedGap = params.get("gap");
  const gap = requestedGap && listed.some((r) => r.skills.includes(requestedGap)) ? requestedGap : null;
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

  const byGap = gap ? listed.filter((r) => r.skills.includes(gap)) : listed;
  const visible = type === "all" ? byGap : byGap.filter((r) => r.type === type);
  const takenShown = plan.resources.filter((r) => r.type === "school_course" && taken.has(r.id)
    && (!gap || r.skills.includes(gap)));
  const school = plan.resources.find((r) => r.school)?.school ?? null;

  return <>
    <RoutePageHeader title="Ways to close your gaps"
      description="Save the ones you’ll actually do. We’ll put them in your action plan in the best order."
      aside={<div className="flex items-center gap-3 rounded-full border border-border bg-card py-1.5 pr-1.5 pl-4 shadow-card">
        <BookmarkCheck aria-hidden className="size-4.5 text-success" />
        {/* Keyed so it mounts at the loaded count instead of rolling up from 0 on every visit. */}
        <span className="font-bold"><NumberFlow key={plan.status} value={plan.items.length} {...numberTiming(280)} /> saved</span>
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
              { key: null, label: "All gaps", count: listed.length },
              ...gapOptions.map((skill) => ({ key: skill, label: skillLabel(skill),
                count: listed.filter((r) => r.skills.includes(skill)).length })),
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
              const courses = key === "school_course" && (type === "all" || type === key);
              const hiddenTaken = courses ? takenShown : [];
              const group = [...visible.filter((r) => r.type === key), ...(showTaken ? hiddenTaken : [])]
                .sort((a, b) => rank(pickOrder, a.id) - rank(pickOrder, b.id)
                  // Courses by code ("COMP SCI 200" before "COMP SCI 300"), whatever order they were added in.
                  || (key === "school_course" ? a.title.localeCompare(b.title, "en", { numeric: true }) : 0));
              if (!group.length && !hiddenTaken.length) return null;
              // Certifications and projects: the top picks up front, the rest under "More …". Student orgs
              // have no picks, so the ones that close the most gaps go on top.
              const picking = key === "certification" || key === "project" ? pending[key] : false;
              const split = key === "certification" || key === "project" || key === "student_org"
                ? splitTopPicks(group, picks, gaps, picking) : null;
              const shown = split ? split.top : group;
              const plural = RESOURCE_TYPES[key].plural.toLowerCase();
              return (
                <section key={key} aria-labelledby={`type-${key}`}>
                  <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <h2 id={`type-${key}`} className="text-section">{typeHeading(key, school)}</h2>
                    <span className="font-mono text-sm">{group.length}</span>
                    <span className="text-sm text-muted-foreground">{RESOURCE_TYPES[key].blurb}</span>
                    {hiddenTaken.length > 0 && <Button size="sm" variant="ghost" className="ml-auto" aria-pressed={showTaken}
                      onClick={() => setShowTaken(!showTaken)}>{showTaken ? "Hide taken" : `Show ${hiddenTaken.length} taken`}</Button>}
                  </div>
                  {courses && <ResumeCourseMatches family={family} courses={plan.resources} />}
                  {courses && justTaken && taken.has(justTaken.id) && <TakenUndo resource={justTaken} onClose={() => setJustTaken(null)} />}
                  {split && picking && !split.top.length && (
                    <p role="status" className="flex items-center gap-2 rounded-2xl border border-border bg-card p-5 text-muted-foreground">
                      <LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />Picking your top {TOP_PICKS} {plural}…
                    </p>
                  )}
                  {shown.length > 0 && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {shown.map((resource) => <ResourceCard key={resource.id}
                      resource={resource} gaps={gaps} recommended={picks.has(resource.id)} onTaken={setJustTaken} />)}
                  </div>}
                  {split && split.more.length > 0 && <MoreResources label={`More ${plural}`}
                    resources={split.more} gaps={gaps} picks={picks} onTaken={setJustTaken} />}
                </section>
              );
            })}
            {visible.length === 0 && <p className="text-muted-foreground">No resources match these filters.</p>}
          </div>
        </div>
      </>}
  </>;
}

function ResourceCard({ resource, gaps, recommended, onTaken }: {
  resource: Resource; gaps: string[]; recommended: boolean; onTaken: (resource: Resource) => void;
}) {
  // Only skills that are gaps, in gap order; strengths it also practices aren't "closed".
  const closes = resource.skills.filter((skill) => gaps.includes(skill))
    .sort((a, b) => rank(gaps, a) - rank(gaps, b)).slice(0, 2);
  return (
    <article className="flex flex-col rounded-2xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center gap-3">
        <ResourceIcon type={resource.type} className="bg-sunken" />
        {/* The section heading already names the school; the Taken button needs the room. */}
        <p className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{resource.type === "school_course" ? null : resource.provider}</p>
        {recommended && <Badge variant="brand">Recommended</Badge>}
        {resource.type === "school_course" && <TakenButton resource={resource} onMarked={onTaken} />}
      </div>
      <h3 className="mt-4 text-title">{resource.title}</h3>
      <p className="mt-1 font-mono text-[0.8125rem] text-muted-foreground">{resource.meta}</p>
      {resource.description && <p className={cn("mt-3 text-sm/6 text-muted-foreground",
        // Course guide descriptions run long; the full text is one click away.
        resource.type === "school_course" && "line-clamp-4")}>{resource.description}</p>}
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
            className={cn("flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left pressable hover:bg-background motion-safe:active:scale-[0.98]",
              option.key === value && "bg-accent font-bold hover:bg-accent")}>
            <span>{option.label}</span><span className="font-mono text-sm">{option.count}</span>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

/** Every certification, project or student org not on top, in a collapsed list whose cards are only built once it's opened. */
function MoreResources({ label, resources, gaps, picks, onTaken }: {
  label: string; resources: Resource[]; gaps: string[]; picks: ReadonlySet<string>; onTaken: (resource: Resource) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <details className="group mt-4 rounded-2xl border border-border bg-card shadow-card"
      onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-2xl px-5 py-4 font-bold hover:bg-background [&::-webkit-details-marker]:hidden">
        <span>{label} <span className="ml-1 font-mono text-sm font-normal text-muted-foreground">{resources.length}</span></span>
        <ChevronDown aria-hidden className="size-4.5 transition-transform group-open:rotate-180" />
      </summary>
      {open && (
        <div className="grid gap-4 border-t border-border p-4 sm:grid-cols-2 xl:grid-cols-3">
          {resources.map((resource) => <ResourceCard key={resource.id}
            resource={resource} gaps={gaps} recommended={picks.has(resource.id)} onTaken={onTaken} />)}
        </div>
      )}
    </details>
  );
}

const NO_PICKS: ReadonlySet<string> = new Set();
/**
 * Ids of the certifications and projects picked for the role's analysis, in pick order.
 * pending is true per type until its picks for this analysis have come back (or failed).
 */
function usePicks(family: JobFamily, runId: string | null) {
  type Loaded = { key: string; ids: string[] };
  const [certifications, setCertifications] = useState<Loaded | null>(null);
  const [projects, setProjects] = useState<Loaded | null>(null);
  const key = `${family}:${runId}`;
  useEffect(() => {
    if (!runId) return;
    let active = true;
    // Each list loads on its own, so slow certification picks don't hold up the project picks.
    // Either can fail on its own (it then counts as loaded with no picks); the catalog still shows everything.
    const load = (request: Promise<string[]>, set: (loaded: Loaded) => void) => {
      void request.then(
        (ids) => { if (active) set({ key, ids }); },
        () => { if (active) set({ key, ids: [] }); },
      );
    };
    load(getCertificationPicks(family).then((response) =>
      response.recommendations.map((pick) => pick.certification_id)), setCertifications);
    // A project pick's reason only restates the skills the card already lists under Closes, so it isn't kept.
    load(getProjectPicks(runId).then((response) =>
      response.recommendations.map((pick) => pick.project_id)), setProjects);
    return () => { active = false; };
  }, [family, runId, key]);
  const certificationPicks = certifications?.key === key ? certifications.ids : null;
  const projectPicks = projects?.key === key ? projects.ids : null;
  const picks = useMemo(
    () => (certificationPicks || projectPicks ? new Set([...(certificationPicks ?? []), ...(projectPicks ?? [])]) : NO_PICKS),
    [certificationPicks, projectPicks],
  );
  return { picks, pending: {
    certification: runId !== null && certificationPicks === null,
    project: runId !== null && projectPicks === null,
  } };
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
