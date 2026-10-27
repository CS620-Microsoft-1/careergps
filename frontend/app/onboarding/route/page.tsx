import type { Metadata } from "next";

import { RouteResult } from "@/components/setup/route-result";
import { SkillGapProvider } from "@/components/skill-gaps/skill-gap-provider";

export const metadata: Metadata = { title: "Your route" };

export default function RoutePage() {
  return (
    <SkillGapProvider>
      <RouteResult />
    </SkillGapProvider>
  );
}
