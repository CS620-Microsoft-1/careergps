"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Award, ExternalLink, LoaderCircle, RotateCcw, Sparkles } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError } from "@/lib/api/client";
import { getCertificationCatalog, getCertificationRecommendations } from "@/lib/api/certifications";
import { SKILL_LABELS } from "@/lib/skill-gap-labels";
import { FAMILY_LABELS } from "@/lib/skill-gap-profile";
import type { Certification, CertificationCatalog, CertificationRecommendations, JobFamily } from "@/types/api";

type Loadable<T> = { key: string; data?: T; error?: string };

const LEVEL_LABELS: Record<Certification["level"], string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

const message = (error: unknown) =>
  error instanceof ApiError ? error.detail ?? error.message : "Something went wrong. Try again.";

function cost(certification: Certification) {
  if (certification.cost_usd === 0) return "Free";
  if (certification.cost_usd === null) return certification.cost_note;
  return `$${certification.cost_usd.toLocaleString()} · ${certification.cost_note}`;
}

/** Certifications tab: personalized picks from the latest skill gap run, then the full list for the direction. */
export function CertificationsPanel() {
  const { loaded, snapshot, family, run, restoring } = useSkillGapAnalysis();
  const [catalog, setCatalog] = useState<Loadable<CertificationCatalog>>({ key: "" });
  const [picks, setPicks] = useState<Loadable<CertificationRecommendations>>({ key: "" });
  const [attempt, setAttempt] = useState(0);

  const completedRun = run?.status === "completed" && run.job_family === family ? run : null;
  const picksKey = completedRun ? `${completedRun.id}:${attempt}` : "";

  useEffect(() => {
    if (!loaded) return;
    let active = true;
    getCertificationCatalog(family).then(
      (data) => active && setCatalog({ key: family, data }),
      (error) => active && setCatalog({ key: family, error: message(error) }),
    );
    return () => { active = false; };
  }, [loaded, family, attempt]);

  useEffect(() => {
    if (!picksKey) return;
    let active = true;
    getCertificationRecommendations(family).then(
      (data) => active && setPicks({ key: picksKey, data }),
      (error) => active && setPicks({ key: picksKey, error: message(error) }),
    );
    return () => { active = false; };
  }, [picksKey, family]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  const currentCatalog = catalog.key === family ? catalog : null;
  const currentPicks = picks.key === picksKey ? picks : null;
  const byId = new Map(currentCatalog?.data?.certifications.map((item) => [item.id, item]));

  if (!loaded) return <p role="status" className="text-muted-foreground">Loading your profile…</p>;

  return (
    <div className="grid gap-6">
      <section className="grid gap-3" aria-labelledby="cert-picks-heading">
        <div>
          <h2 id="cert-picks-heading" className="text-lg font-semibold">Recommended for you</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Based on your highest-priority {FAMILY_LABELS[family]} skill gaps.
          </p>
        </div>
        <Recommendations
          family={family}
          hasResume={Boolean(snapshot)}
          runStatus={restoring ? "restoring" : run?.job_family === family ? run.status : null}
          picks={currentPicks}
          byId={byId}
          catalogReady={Boolean(currentCatalog?.data)}
          onRetry={retry}
        />
      </section>

      <section className="grid gap-3" aria-labelledby="cert-all-heading">
        <h2 id="cert-all-heading" className="text-lg font-semibold">
          All certifications for {FAMILY_LABELS[family]}
        </h2>
        {!currentCatalog ? (
          <p role="status" className="text-sm text-muted-foreground">Loading certifications…</p>
        ) : currentCatalog.error ? (
          <ErrorNotice text={currentCatalog.error} onRetry={retry} />
        ) : currentCatalog.data?.certifications.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {currentCatalog.data.certifications.map((item) => (
              <CertificationCard key={item.id} certification={item} skillIds={item.skills[family] ?? []} />
            ))}
          </div>
        ) : (
          <Card><EmptyState icon={Award} title="No certifications listed for this direction yet" /></Card>
        )}
      </section>
    </div>
  );
}

function Recommendations({ family, hasResume, runStatus, picks, byId, catalogReady, onRetry }: {
  family: JobFamily;
  hasResume: boolean;
  runStatus: "restoring" | "queued" | "running" | "completed" | "failed" | null;
  picks: Loadable<CertificationRecommendations> | null;
  byId: Map<string, Certification>;
  catalogReady: boolean;
  onRetry: () => void;
}) {
  if (!hasResume) {
    return <Card><EmptyState icon={Sparkles} title="Confirm your résumé first"
      description="Recommendations use the skill gaps found in your confirmed résumé."
      action={<Button asChild><Link href="/onboarding">Upload and review résumé</Link></Button>} /></Card>;
  }
  if (runStatus === "restoring") {
    return <p role="status" className="text-sm text-muted-foreground">Loading your skill gap analysis…</p>;
  }
  if (runStatus === "queued" || runStatus === "running") {
    return <Card><CardContent className="flex items-center gap-3 text-sm">
      <LoaderCircle className="size-5 shrink-0 animate-spin text-primary" />
      Your skill gap analysis is still running. Recommendations appear when it finishes.
    </CardContent></Card>;
  }
  if (runStatus !== "completed") {
    return <Card><EmptyState icon={Sparkles}
      title={runStatus === "failed" ? "Your last skill gap analysis didn't finish" : "Run a skill gap analysis first"}
      description={`Recommendations are matched to your ${FAMILY_LABELS[family]} skill gaps.`}
      action={<Button asChild><Link href="/gaps">Go to Skill Gaps</Link></Button>} /></Card>;
  }
  if (!picks || !catalogReady) {
    return <Card><CardContent className="flex items-center gap-3 text-sm text-muted-foreground" role="status">
      <LoaderCircle className="size-5 shrink-0 animate-spin text-primary" />
      Matching certifications to your gaps. The first time can take up to 30 seconds.
    </CardContent></Card>;
  }
  if (picks.error) return <ErrorNotice text={picks.error} onRetry={onRetry} />;

  const items = picks.data?.recommendations.filter((item) => byId.has(item.certification_id)) ?? [];
  if (!items.length) {
    return <Card><EmptyState icon={Award} title="No matching certification yet"
      description="None of the certifications we track covers your top gaps. Check the full list below." /></Card>;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {items.map((item) => (
        <CertificationCard key={item.certification_id} certification={byId.get(item.certification_id)!}
          skillIds={item.skill_ids} reason={item.reason} highlighted />
      ))}
    </div>
  );
}

function CertificationCard({ certification, skillIds, reason, highlighted = false }: {
  certification: Certification;
  skillIds: string[];
  reason?: string | null;
  highlighted?: boolean;
}) {
  return (
    <Card className={highlighted ? "border-primary/30" : undefined}>
      <CardContent className="grid gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-semibold">{certification.name}</h3>
            <p className="text-xs text-muted-foreground">{certification.provider}</p>
          </div>
          <Badge variant={certification.level === "beginner" ? "success" : certification.level === "advanced" ? "warning" : "brand"}>
            {LEVEL_LABELS[certification.level]}
          </Badge>
        </div>
        {reason && <p className="text-sm">{reason}</p>}
        <div className="flex flex-wrap gap-1.5" aria-label={highlighted ? "Gaps it closes" : "Skills covered"}>
          {skillIds.map((id) => <Badge key={id} variant="outline">{SKILL_LABELS[id] ?? id}</Badge>)}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>{cost(certification)}</span>
          <Button asChild variant="ghost" size="sm">
            <a href={certification.url} target="_blank" rel="noopener noreferrer">
              View certification<ExternalLink data-icon="inline-end" />
            </a>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ErrorNotice({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger">
      {text}
      <Button variant="outline" size="sm" onClick={onRetry}><RotateCcw data-icon="inline-start" />Try again</Button>
    </div>
  );
}
