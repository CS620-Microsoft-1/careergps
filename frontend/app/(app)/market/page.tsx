import type { Metadata } from "next";
import { ChartColumn, ChevronRight, ListChecks } from "lucide-react";

import { AgentPipeline } from "@/components/common/agent-pipeline";
import { ComingSoon } from "@/components/common/coming-soon";
import { EmptyState } from "@/components/common/empty-state";
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
import { Select, SelectTrigger, SelectValue } from "@/components/ui/select";
import { INITIAL_PIPELINE } from "@/lib/agents";

export const metadata: Metadata = { title: "Career Analysis" };

const FILTERS = ["Target role", "New grad / Entry level", "United States", "Last 90 days"];

/** Market filters, shown but inactive until there is market data to filter. */
function Filters() {
  return (
    <ComingSoon className="flex-wrap gap-2">
      {FILTERS.map((label) => (
        <Select key={label} disabled>
          <SelectTrigger size="sm" aria-label={label} className="bg-card">
            <SelectValue placeholder={label} />
          </SelectTrigger>
        </Select>
      ))}
    </ComingSoon>
  );
}

export default function MarketPage() {
  return (
    <>
      <PageHeader
        title="Career Analysis"
        description="What employers are looking for in your target role."
        actions={<Filters />}
      />

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Skill demand</CardTitle>
            <CardDescription>Share of postings that mention each skill</CardDescription>
          </CardHeader>
          <CardContent>
            <EmptyState
              icon={ChartColumn}
              title="No market data yet"
              description="Once your target role is analyzed, the most requested skills appear here with their share of postings."
            />
          </CardContent>
        </Card>

        <div className="grid content-start gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Common responsibilities</CardTitle>
            </CardHeader>
            <CardContent>
              <EmptyState
                icon={ListChecks}
                title="Nothing to show yet"
                description="Typical day-to-day work for your target role will be summarized here."
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>How this was generated</CardTitle>
              <CardDescription>Four agents, run in sequence</CardDescription>
              <CardAction>
                <ComingSoon>
                  <Button variant="link" disabled className="h-auto p-0">
                    Details <ChevronRight data-icon="inline-end" />
                  </Button>
                </ComingSoon>
              </CardAction>
            </CardHeader>
            <CardContent>
              <AgentPipeline steps={INITIAL_PIPELINE} />
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
