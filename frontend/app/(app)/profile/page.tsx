import type { Metadata } from "next";
import Link from "next/link";
import { CircleCheck } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PLACEHOLDER_USER } from "@/lib/placeholder-user";

export const metadata: Metadata = { title: "Your Profile" };

const SKILL_COLUMNS = [
  { title: "Strong", dot: "bg-success" },
  { title: "Some experience", dot: "bg-warning-fill" },
  { title: "Not yet demonstrated", dot: "bg-danger" },
];

export default function ProfilePage() {
  const user = PLACEHOLDER_USER;

  return (
    <>
      <PageHeader title="Your Profile" description="What CareerGPS found in your résumé." />

      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-center gap-4">
          <Avatar size="lg">
            <AvatarFallback>{user.initials}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1 basis-48">
            <h2 className="text-base">{user.name}</h2>
            <p className="text-muted-foreground">No résumé uploaded yet</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge>Target role not set</Badge>
              <Badge>Graduation year not set</Badge>
            </div>
          </div>
          <Button asChild variant="outline">
            <Link href="/onboarding">Upload résumé</Link>
          </Button>
        </CardContent>
      </Card>

      <p className="mb-4 flex items-center gap-2.5 rounded-lg bg-accent px-3.5 py-2.5 text-control text-accent-foreground">
        <CircleCheck aria-hidden className="size-4 shrink-0" />
        Skills are rated by demonstrated evidence, not keywords.
      </p>

      <div className="grid items-start gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {SKILL_COLUMNS.map(({ title, dot }) => (
          <Card key={title} size="sm">
            <CardContent>
              <h3 className="flex items-center gap-2 text-sm">
                <span aria-hidden className={`size-2 rounded-full ${dot}`} />
                {title}
                <span className="ml-auto font-normal text-muted-foreground">0</span>
              </h3>
              <p className="mt-3 border-t border-line-soft pt-3 text-control text-muted-foreground">
                Skills will appear here after your résumé is analyzed.
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
