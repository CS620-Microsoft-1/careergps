import type { Metadata } from "next";
import Link from "next/link";
import { ChartColumn } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = { title: "Skill Gaps" };

const COLUMNS = ["Skill", "Market demand", "Your evidence", "Recommended action"];

export default function GapsPage() {
  return (
    <>
      <PageHeader
        title="Skill Gaps"
        description="Prioritized by market demand and your demonstrated experience."
      />

      <Card className="gap-0 py-0">
        {/* Column headings match the future table; hidden on small screens like the prototype. */}
        <div
          aria-hidden
          className="hidden grid-cols-[1.1fr_0.9fr_1fr_1.8fr_7rem] gap-5 rounded-t-xl border-b border-line-soft bg-[#fafbfb] px-5 py-2.5 text-xs font-medium text-muted-foreground md:grid"
        >
          {COLUMNS.map((c) => (
            <span key={c}>{c}</span>
          ))}
        </div>
        <EmptyState
          icon={ChartColumn}
          title="No skill gaps yet"
          description="Once your résumé is compared with the job market, your gaps appear here ranked by priority, with a recommended action for each."
          action={
            <Button asChild>
              <Link href="/onboarding">Upload résumé</Link>
            </Button>
          }
          className="py-12"
        />
      </Card>
    </>
  );
}
