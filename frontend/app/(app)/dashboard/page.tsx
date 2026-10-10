import type { Metadata } from "next";
import Link from "next/link";
import { ChartColumn, ChevronRight, Gauge, Sparkles, Target } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { StatCard } from "@/components/common/stat-card";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Welcome to CareerGPS"
        description="Here's how you'll compare with the job market for your target role."
        actions={
          <div className="flex items-center gap-2.5 rounded-lg border bg-card py-1.5 pr-1.5 pl-3 text-control">
            <Target aria-hidden className="size-4" />
            <span className="font-semibold">No target role yet</span>
            <Button asChild size="sm" variant="secondary" className="bg-background">
              <Link href="/onboarding">Set goal</Link>
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Career readiness" value="—" detail="Available after your first analysis" />
        <StatCard label="Jobs analyzed" value="—" detail="Entry-level postings, last 90 days" />
        <StatCard label="High-priority gaps" value="—" detail="Identified after your first analysis" />
        <StatCard label="Plan progress" value="—">
          <Progress value={0} aria-label="Plan progress" className="mt-2.5" />
        </StatCard>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-4 rounded-xl bg-deep px-5 py-4.5 text-deep-foreground">
        <span className="grid size-9 place-items-center rounded-lg bg-white/12">
          <Sparkles aria-hidden className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1 basis-56">
          <p className="text-xs text-deep-muted">Recommended next step</p>
          <p className="text-title font-semibold">Upload your résumé to get your first analysis</p>
        </div>
        <Button asChild variant="outline" className="border-0 text-foreground">
          <Link href="/onboarding">
            Get started <ChevronRight data-icon="inline-end" />
          </Link>
        </Button>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Readiness breakdown</CardTitle>
            <CardDescription>Not analyzed yet</CardDescription>
          </CardHeader>
          <CardContent>
            <EmptyState
              icon={Gauge}
              title="No readiness score yet"
              description="Technical skills, projects, experience, cloud and AI/ML readiness will be scored here."
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Priority skill gaps</CardTitle>
            <CardDescription>Ranked by career impact</CardDescription>
            <CardAction>
              <Button asChild variant="link" className="h-auto p-0">
                <Link href="/gaps">
                  View all <ChevronRight data-icon="inline-end" />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            <EmptyState
              icon={ChartColumn}
              title="No gaps identified yet"
              description="Your most important skill gaps will be listed here."
            />
          </CardContent>
        </Card>
      </div>
    </>
  );
}
