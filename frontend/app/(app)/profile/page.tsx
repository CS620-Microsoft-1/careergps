import type { Metadata } from "next";

import { PageHeader } from "@/components/layout/page-header";
import { ProfileView } from "@/components/profile/profile-view";

export const metadata: Metadata = { title: "Your Profile" };

export default function ProfilePage() {
  return (
    <>
      <PageHeader title="Your Profile" description="What CareerGPS found in your résumé." />
      <ProfileView />
    </>
  );
}
