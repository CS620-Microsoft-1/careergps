"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BookmarkCheck, Check, ChevronRight, ExternalLink, Layers, LoaderCircle } from "lucide-react";

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
  const { run, snapshot, loaded, family } = useSkillGapAnalysis();
  const { user } = useAccount();
  const plan = usePlan();
  const [type, setType] = useState<ResourceType | "all">("all");

  const report = run?.status === "completed" ? run.report : null;
  const picks = usePicks(family, report ? run!.id : null);
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
              return (
                <section key={key} aria-labelledby={`type-${key}`}>
                  <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <h2 id={`type-${key}`} className="text-section">{typeHeading(key, school)}</h2>
                    <span className="font-mono text-sm">{group.length}</span>
                    <span className="text-sm text-muted-foreground">{RESOURCE_TYPES[key].blurb}</span>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {group.map((resource) => <ResourceCard key={resource.id} resource={resource} gaps={gaps} pick={picks.get(resource.id)} />)}
                  </div>
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
  // The gaps it closes first, in gap order, then anything else it covers.
  const closes = [...resource.skills].sort((a, b) => rank(gaps, a) - rank(gaps, b)).slice(0, 2);
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
      <p className="mt-auto pt-4 text-sm">Closes: <b>{closes.map(skillLabel).join(", ")}</b></p>
      <div className="mt-4 flex items-center gap-2">
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

const NO_PICKS = new Map<string, string | null>();

/** Certification and project picks for the role's analysis: resource id → reason, in pick order. */
function usePicks(family: JobFamily, runId: string | null) {
  const [picks, setPicks] = useState<{ runId: string; byId: Map<string, string | null> } | null>(null);
  useEffect(() => {
    if (!runId) return;
    let active = true;
    // Either list can fail on its own; the catalog below still shows everything.
    void Promise.allSettled([getCertificationPicks(family), getProjectPicks(runId)]).then(([certifications, projects]) => {
      if (!active) return;
      const byId = new Map<string, string | null>();
      if (certifications.status === "fulfilled") {
        for (const pick of certifications.value.recommendations) byId.set(pick.certification_id, pick.reason);
      }
      if (projects.status === "fulfilled") {
        for (const pick of projects.value.recommendations) byId.set(pick.project_id, pick.why_recommended);
      }
      setPicks({ runId, byId });
    });
    return () => { active = false; };
  }, [family, runId]);
  return picks?.runId === runId ? picks.byId : NO_PICKS;
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
