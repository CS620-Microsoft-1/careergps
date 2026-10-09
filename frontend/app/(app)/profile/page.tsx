import type { Metadata } from "next";

import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Your Profile" };

export default function ProfilePage() {
  return <PageHeader title="Your Profile" description="What CareerGPS found in your résumé." />;
}
