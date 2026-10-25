"use client";

import { useState } from "react";
import { ChartColumn, ListChecks, LoaderCircle, RotateCcw } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { MarketDemandChart } from "@/components/market/market-demand-chart";
import { MarketPipeline } from "@/components/market/market-pipeline";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FAMILY_LABELS } from "@/lib/confirmed-resume";
import { useMarketDemand } from "@/lib/use-market-demand";
import type { JobFamily } from "@/types/api";

export function MarketWorkspace() {
  const { loaded, snapshot, family, run, submitting, restoring, changeFamily } = useSkillGapAnalysis();
  const [browseFamily, setBrowseFamily] = useState<JobFamily>("software_engineer");
  const selectedFamily = snapshot ? family : browseFamily;
  const { data, loading, error, reload } = useMarketDemand(loaded ? selectedFamily : null);
  const busy = submitting || restoring || run?.status === "queued" || run?.status === "running";
  const selectFamily = (value: string) => {
    if (busy || !Object.hasOwn(FAMILY_LABELS, value)) return;
    if (snapshot) changeFamily(value);
    else setBrowseFamily(value as JobFamily);
  };

  return <>
    <PageHeader title="Career Analysis" description="What employers are looking for in your target role."
      actions={<div className="flex flex-wrap gap-2">
        <Select value={selectedFamily} onValueChange={selectFamily} disabled={!loaded || busy}>
          <SelectTrigger size="sm" aria-label="Target role" className="bg-card"><SelectValue placeholder="Target role" /></SelectTrigger>
          <SelectContent>{Object.entries(FAMILY_LABELS).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent>
        </Select>
        {["All levels", "All locations", "Fixed snapshot"].map((label) => <Select key={label} disabled>
          <SelectTrigger size="sm" aria-label={label} className="bg-card" title="This snapshot can currently be filtered by target role only."><SelectValue placeholder={label} /></SelectTrigger>
        </Select>)}
      </div>} />

    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
      <Card>
        <CardHeader><CardTitle>Skill demand</CardTitle><CardDescription>{data
          ? `${data.sample_size.toLocaleString()} ${FAMILY_LABELS[selectedFamily]} postings · ${data.core_skill_count} core skills`
          : "Share of postings that mention each skill"}</CardDescription></CardHeader>
        <CardContent>
          {loading || !loaded ? <div role="status" className="flex min-h-64 flex-col items-center justify-center gap-3 text-sm text-muted-foreground"><LoaderCircle aria-hidden="true" className="size-6 motion-safe:animate-spin text-primary" /><p>Loading market demand…</p></div>
            : error ? <div role="alert" className="grid min-h-64 content-center justify-items-center gap-3 text-center"><p className="font-medium">Market demand could not be loaded</p><p className="max-w-80 text-sm text-muted-foreground">{error}</p><Button variant="outline" size="sm" onClick={reload}><RotateCcw data-icon="inline-start" />Try loading again</Button></div>
            : data ? <MarketDemandChart key={data.job_family} snapshot={data} />
            : <EmptyState icon={ChartColumn} title="No market data yet" description="Choose a target role to view its saved skill-demand snapshot." />}
        </CardContent>
      </Card>
      <div className="grid content-start gap-4">
        <Card><CardHeader><CardTitle>Common responsibilities</CardTitle></CardHeader><CardContent>
          <EmptyState icon={ListChecks} title="Responsibilities not available yet" description="The current snapshot contains skill requirements. A summary of day-to-day responsibilities has not been provided." />
        </CardContent></Card>
        <Card><CardHeader><CardTitle>How this was generated</CardTitle><CardDescription>Current analysis stages</CardDescription></CardHeader><CardContent>
          <MarketPipeline confirmed={Boolean(snapshot)} marketLoaded={Boolean(data)} marketLoading={loading} marketError={error} run={run} submitting={submitting} />
        </CardContent></Card>
      </div>
    </div>
  </>;
}
