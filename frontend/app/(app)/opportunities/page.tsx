import type { Metadata } from "next";
import { BookOpen, CalendarDays, FolderGit2, GraduationCap, Users, type LucideIcon } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const metadata: Metadata = { title: "Resources" };

const TABS: { value: string; label: string; noun: string; icon: LucideIcon; empty: string }[] = [
  {
    value: "projects",
    label: "Projects",
    noun: "project",
    icon: FolderGit2,
    empty: "Portfolio projects that close several of your gaps at once.",
  },
  {
    value: "courses",
    label: "Courses",
    noun: "course",
    icon: GraduationCap,
    empty: "UW–Madison courses matched to the skills employers ask for.",
  },
  {
    value: "clubs",
    label: "Clubs",
    noun: "club",
    icon: Users,
    empty: "Student organizations where you can practice in-demand skills.",
  },
  {
    value: "events",
    label: "Events",
    noun: "event",
    icon: CalendarDays,
    empty: "Hackathons, project marathons and competitions worth joining.",
  },
  {
    value: "learning",
    label: "Free learning",
    noun: "free learning",
    icon: BookOpen,
    empty: "Free online courses for each of your high-priority gaps.",
  },
];

export default function OpportunitiesPage() {
  return (
    <>
      <PageHeader
        title="Resources"
        description="Projects, courses, and communities that turn your gaps into demonstrated skills."
      />

      <Tabs defaultValue="projects" className="gap-5">
        <TabsList>
          {TABS.map(({ value, label }) => (
            <TabsTrigger key={value} value={value}>
              {label}
              <span className="font-medium text-muted-foreground">0</span>
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map(({ value, noun, icon, empty }) => (
          <TabsContent key={value} value={value}>
            <Card>
              <EmptyState
                icon={icon}
                title={`No ${noun} recommendations yet`}
                description={`${empty} Recommendations appear after your first analysis.`}
              />
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </>
  );
}
