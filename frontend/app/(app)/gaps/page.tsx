import type { Metadata } from "next";

import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Skill Gaps" };

export default function GapsPage() {
  return <PageHeader title="Skill Gaps" description="Prioritized by market demand and your demonstrated experience." />;
}
