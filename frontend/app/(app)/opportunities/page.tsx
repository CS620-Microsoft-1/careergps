import type { Metadata } from "next";

import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Resources" };

export default function OpportunitiesPage() {
  return <PageHeader title="Resources" description="Projects, courses, and communities that turn your gaps into demonstrated skills." />;
}
