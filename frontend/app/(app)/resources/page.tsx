import type { Metadata } from "next";
import { Suspense } from "react";

import { ResourcesView } from "@/components/resources/resources-view";

export const metadata: Metadata = { title: "Resources" };

export default function ResourcesPage() {
  // ?gap= is read in the browser (useSearchParams), so the view renders below a Suspense boundary.
  return (
    <Suspense fallback={<p className="text-muted-foreground">Loading resources…</p>}>
      <ResourcesView />
    </Suspense>
  );
}
