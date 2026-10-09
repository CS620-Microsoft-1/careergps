import type { Metadata } from "next";
import Link from "next/link";
import { ClipboardList } from "lucide-react";

import { ComingSoon } from "@/components/common/coming-soon";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export const metadata: Metadata = { title: "Action Plan" };

export default function RoadmapPage() {
  return (
    <>
      <PageHeader
        title="Action Plan"
        description="A week-by-week roadmap built from your highest-impact gaps."
        actions={
          <div className="flex flex-wrap gap-2">
            <ComingSoon>
              <Button variant="outline" disabled>
                Create GitHub Issues
              </Button>
            </ComingSoon>
            <ComingSoon>
              <Button disabled>Start Project</Button>
            </ComingSoon>
          </div>
        }
      />

      <Card>
        <CardContent className="grid items-center gap-8 md:grid-cols-[minmax(0,1fr)_15rem]">
          <div>
            <Badge variant="brand">Highest-impact next step</Badge>
            <h2 className="mt-2 mb-1.5 text-[1.1875rem]">No plan yet</h2>
            <p className="text-muted-foreground">
              Your plan is built around the project that closes the most skill gaps.
            </p>
          </div>
          <div>
            <p>
              <b className="text-page-title font-semibold tracking-[-0.02em]">0</b>{" "}
              <span className="text-muted-foreground">/ 0 tasks done</span>
            </p>
            <Progress value={0} aria-label="Tasks done" className="mt-2" />
          </div>
        </CardContent>
      </Card>

      <Card className="mt-4">
        <EmptyState
          icon={ClipboardList}
          title="Your weekly plan will appear here"
          description="Each week lists concrete tasks you can check off as you go."
          action={
            <Button asChild variant="outline">
              <Link href="/onboarding">Upload résumé</Link>
            </Button>
          }
          className="py-12"
        />
      </Card>
    </>
  );
}
