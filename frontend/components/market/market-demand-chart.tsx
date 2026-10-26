"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { SKILL_LABELS } from "@/lib/skill-gap-labels";
import type { MarketDemandSkill, MarketDemandSnapshot } from "@/types/api";

const percent = (ratio: number) => `${(ratio * 100).toFixed(1)}%`;

export function rankMarketSkills(skills: MarketDemandSkill[]) {
  return [...skills].sort((a, b) => (b.required_ratio + b.preferred_only_ratio) -
    (a.required_ratio + a.preferred_only_ratio) || a.skill_id.localeCompare(b.skill_id));
}

export function MarketDemandChart({ snapshot }: { snapshot: MarketDemandSnapshot }) {
  const [expanded, setExpanded] = useState(false);
  const ordered = rankMarketSkills(snapshot.skills);
  const visible = expanded ? ordered : ordered.slice(0, 10);
  return <>
    <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
      <Legend color="bg-primary" label="Required" /><Legend color="bg-primary/40" label="Preferred only" /><Legend color="bg-muted-foreground/35" label="Level unspecified" />
    </div>
    <div className="grid gap-5">
      {visible.map((skill) => {
        const name = SKILL_LABELS[skill.skill_id] ?? skill.skill_id.replaceAll("_", " ");
        return <div key={skill.skill_id}>
          <p className="mb-2 text-control font-medium">{name}</p>
          <div className="flex h-2 overflow-hidden rounded-full bg-muted" role="img"
            aria-label={`${name}: ${percent(skill.required_ratio)} required, ${percent(skill.preferred_only_ratio)} preferred only, ${percent(skill.unspecified_ratio)} level unspecified`}>
            <span className="bg-primary" style={{ width: percent(skill.required_ratio) }} />
            <span className="bg-primary/40" style={{ width: percent(skill.preferred_only_ratio) }} />
            <span className="bg-muted-foreground/35" style={{ width: percent(skill.unspecified_ratio) }} />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
            <span>Required <span className="font-medium text-foreground">{percent(skill.required_ratio)}</span></span>
            <span>Preferred <span className="font-medium text-foreground">{percent(skill.preferred_only_ratio)}</span></span>
            <span>Unspecified <span className="font-medium text-foreground">{percent(skill.unspecified_ratio)}</span></span>
          </div>
        </div>;
      })}
    </div>
    {ordered.length > 10 && <Button variant="ghost" size="sm" className="mt-5 w-full" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      {expanded ? "Show top 10 skills" : `Show all ${ordered.length} skills`}
    </Button>}
    <p className="mt-4 text-xs leading-relaxed text-muted-foreground">Each share uses the same {snapshot.sample_size.toLocaleString()}-posting sample. Skills are sorted by required plus preferred demand; unspecified requirements are shown separately.</p>
    <div className="mt-3 border-t border-line-soft pt-3 text-xs leading-relaxed text-muted-foreground">
      <p>Fixed export snapshot · calculated {new Date(snapshot.snapshot_generated_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" })}.</p>
      <p>Posting date window: {snapshot.posting_window ?? "unknown"}. Company coverage: {snapshot.company_coverage ?? "unknown"}.</p>
      <p>{snapshot.source_description}</p>
      {snapshot.coverage_limitations.length > 0 && <ul className="mt-1 list-disc pl-4">{snapshot.coverage_limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
    </div>
  </>;
}

function Legend({ color, label }: { color: string; label: string }) {
  return <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className={`size-2 rounded-full ${color}`} />{label}</span>;
}
