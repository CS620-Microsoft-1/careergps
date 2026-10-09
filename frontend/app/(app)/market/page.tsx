import type { Metadata } from "next";

import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Career Analysis" };

export default function MarketPage() {
  return <PageHeader title="Career Analysis" description="What employers are looking for in your target role." />;
}
