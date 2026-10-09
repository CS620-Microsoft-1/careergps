import type { Metadata } from "next";

import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return <PageHeader title="Welcome to CareerGPS" description="Your career overview will appear here after your first analysis." />;
}
