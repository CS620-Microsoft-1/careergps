import type { Metadata } from "next";

import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Action Plan" };

export default function RoadmapPage() {
  return <PageHeader title="Action Plan" description="A step-by-step roadmap built from your highest-impact gaps." />;
}
