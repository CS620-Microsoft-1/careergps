import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { SkillGapsWorkspace } from "@/components/skill-gaps/skill-gaps-workspace";

export const metadata: Metadata = { title: "Skill Gaps" };

export default function GapsPage() {
  return (
    <>
      <PageHeader
        title="Skill Gaps"
        description="Compare your confirmed résumé evidence with the demand for your selected direction."
      />

      <SkillGapsWorkspace />
    </>
  );
}
