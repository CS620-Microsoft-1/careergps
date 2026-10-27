import type { Metadata } from "next";

import { GapsView } from "@/components/gaps/gaps-view";

export const metadata: Metadata = { title: "Gaps" };

export default function GapsPage() {
  return <GapsView />;
}
