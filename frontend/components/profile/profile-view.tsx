"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CircleCheck } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getMe, getSavedResume } from "@/lib/api/me";
import { getSupabase } from "@/lib/supabase/client";
import type { MeResponse, ResumeClassification, ResumeRecord, SavedResume } from "@/types/api";

type ProfileState = {
  status: "loading" | "ready";
  email: string | null;
  me: MeResponse | null;
  saved: SavedResume | null;
};

// Placeholder until skill ratings come from the gap analysis (ADR-001); the résumé alone has no evidence levels.
const SKILL_COLUMNS = [
  { title: "Strong", dot: "bg-success" },
  { title: "Some experience", dot: "bg-warning-fill" },
  { title: "Not yet demonstrated", dot: "bg-danger" },
];

export function ProfileView() {
  const [state, setState] = useState<ProfileState>({
    status: "loading",
    email: null,
    me: null,
    saved: null,
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let email: string | null = null;
      let saved: SavedResume | null = null;
      let me: MeResponse | null = null;
      try {
        const { data } = await getSupabase().auth.getUser();
        if (data.user) {
          email = data.user.email ?? null;
          // The page still works from Supabase alone if the API is down.
          [me, saved] = await Promise.all([
            getMe().catch(() => null),
            getSavedResume().catch(() => null),
          ]);
        }
      } catch {
        // No Supabase session or config: show the empty state.
      }
      if (!cancelled) setState({ status: "ready", email, me, saved });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const classification = state.saved?.classification;

  return (
    <>
      <IdentityCard state={state} />

      {state.status === "ready" && (
        <>
          <p className="mb-4 flex items-center gap-2.5 rounded-lg bg-accent px-3.5 py-2.5 text-control text-accent-foreground">
            <CircleCheck aria-hidden className="size-4 shrink-0" />
            Skills are rated by demonstrated evidence, not keywords.
          </p>

          <SkillColumns />

          {classification && <ResumeSections classification={classification} />}
        </>
      )}
    </>
  );
}

function IdentityCard({ state }: { state: ProfileState }) {
  const { me, saved, email } = state;
  const personal = saved?.classification.personal_information;

  const resumeName = text(personal?.name);
  const user = me?.user;
  const accountName = user ? `${user.first_name} ${user.last_name}`.trim() : "";
  const name =
    accountName || user?.full_name?.trim() || resumeName || email?.split("@")[0] || (state.status === "loading" ? "" : "Student");
  const initials = initialsOf(name || email || "S");

  const targetRole = user?.target_role ?? null;
  const experienceLevel = user?.experience_level ?? null;
  const graduationYear = user?.graduation_year?.toString() ?? null;
  const location = user?.preferred_location ?? text(personal?.location);
  const university = user?.university ?? null;

  const contacts = [
    ...list(personal?.phones),
    text(personal?.linkedin),
    text(personal?.github),
    text(personal?.website),
  ].filter(Boolean);

  return (
    <Card className="mb-4">
      <CardContent className="flex flex-wrap items-center gap-4">
        <Avatar size="lg">
          <AvatarFallback>{initials}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1 basis-48">
          <h2 className="text-base">{name || "Loading your profile…"}</h2>
          {email && <p className="truncate text-control text-ink-2">{email}</p>}
          {state.status === "ready" && (
            <p className="text-muted-foreground">
              {saved
                ? `Résumé: ${saved.original_filename} · saved ${formatSavedAt(saved.created_at)}`
                : "No résumé uploaded yet"}
            </p>
          )}
          {state.status === "ready" && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge variant={targetRole ? "brand" : "default"}>{targetRole ?? "Target role not set"}</Badge>
              {experienceLevel && <Badge>{experienceLevel}</Badge>}
              <Badge>{graduationYear ? `Class of ${graduationYear}` : "Graduation year not set"}</Badge>
              {university && <Badge>{university}</Badge>}
              {location && <Badge>{location}</Badge>}
            </div>
          )}
          {contacts.length > 0 && (
            <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {contacts.map((item) => (
                <span key={item} className="break-all">
                  {item}
                </span>
              ))}
            </p>
          )}
        </div>
        {state.status === "ready" && (
          <Button asChild variant="outline">
            <Link href="/onboarding">{saved ? "Upload a new résumé" : "Upload résumé"}</Link>
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function SkillColumns() {
  return (
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
              Skill ratings will appear here once the gap analysis is ready.
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

type Entry = { key: string; title: string; subtitle?: string; meta?: string; details: string[] };

function ResumeSections({ classification: c }: { classification: ResumeClassification }) {
  const sections: { title: string; entries: Entry[] }[] = [
    {
      title: "Experience",
      entries: [
        ...c.work_experience.map((r, i) =>
          entry(`work-${i}`, r.title, [r.company, r.location], dates(r), r.content),
        ),
        ...c.research_experience.map((r, i) =>
          entry(`research-${i}`, r.title, ["Research", r.organization, r.location], dates(r), r.content),
        ),
      ],
    },
    {
      title: "Education",
      entries: c.education.map((r, i) =>
        entry(
          `edu-${i}`,
          r.institution,
          [[text(r.degree), text(r.major)].filter(Boolean).join(", "), text(r.gpa) && `GPA ${text(r.gpa)}`],
          dates(r),
          r.content,
        ),
      ),
    },
    {
      title: "Projects",
      entries: c.projects.map((r, i) =>
        entry(`project-${i}`, r.name, [list(r.technologies).join(", ")], text(r.url), r.content),
      ),
    },
    {
      title: "Leadership and Activities",
      entries: c.leadership_activities.map((r, i) =>
        entry(`lead-${i}`, r.role, [r.organization, r.location], dates(r), r.content),
      ),
    },
    {
      title: "Certifications",
      entries: c.certifications.map((r, i) => entry(`cert-${i}`, r.name, [r.issuer], text(r.date), r.content)),
    },
    {
      title: "Awards and Honors",
      entries: c.awards_honors.map((r, i) => entry(`award-${i}`, r.name, [r.issuer], text(r.date), r.content)),
    },
    {
      title: "Publications",
      entries: c.publications.map((r, i) =>
        entry(`pub-${i}`, r.title, [r.authors, r.venue], text(r.date), r.content),
      ),
    },
    {
      title: "Languages",
      entries: c.languages.map((r, i) => entry(`lang-${i}`, r.name, [r.proficiency], "", [])),
    },
    {
      title: "Research Interests",
      entries: c.research_interests.filter(Boolean).map((item, i) => entry(`interest-${i}`, item, [], "", [])),
    },
    {
      // What the classifier couldn't place, e.g. a professional summary.
      title: "More from your résumé",
      entries: c.other.map((r, i) => {
        const [first, ...rest] = text(r.content).split("\n");
        return entry(`other-${i}`, sentenceCase(first), [], "", rest);
      }),
    },
  ].filter((section) => section.entries.length > 0);

  if (sections.length === 0) return null;

  return (
    <div className="mt-4 grid items-start gap-4 lg:grid-cols-2">
      {sections.map((section) => (
        <Card key={section.title} size="sm">
          <CardHeader>
            <CardTitle>{section.title}</CardTitle>
            <CardDescription>From your résumé</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-3">
              {section.entries.map((item) => (
                <li key={item.key} className="border-t border-line-soft pt-3 first:border-t-0 first:pt-0">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <p className="text-control font-semibold">{item.title}</p>
                    {item.meta && <p className="text-xs break-all text-muted-foreground">{item.meta}</p>}
                  </div>
                  {item.subtitle && <p className="text-control text-ink-2">{item.subtitle}</p>}
                  {item.details.length > 0 && (
                    <ul className="mt-1.5 grid list-disc gap-1 pl-4 text-control text-ink-2">
                      {item.details.map((detail, i) => (
                        <li key={i}>{detail}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

type Value = ResumeRecord[string] | undefined;

function entry(key: string, title: Value, subtitle: Value[], meta: string, details: Value): Entry {
  return {
    key,
    title: text(title) || "Untitled",
    subtitle: subtitle.map(text).filter(Boolean).join(" · ") || undefined,
    meta: meta || undefined,
    details: list(details),
  };
}

function dates(record: ResumeRecord) {
  const start = formatMonth(text(record.start_date));
  const end = formatMonth(text(record.end_date));
  return start && end ? `${start} – ${end}` : start || end;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2022-03" → "Mar 2022"; "2022" and "Present" stay as they are. */
function formatMonth(value: string) {
  const match = /^(\d{4})-(\d{2})$/.exec(value);
  const month = match ? MONTHS[Number(match[2]) - 1] : undefined;
  return match && month ? `${month} ${match[1]}` : value;
}

function formatSavedAt(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? "earlier"
    : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

/** "PROFESSIONAL SUMMARY" → "Professional summary". Mixed-case text (e.g. "iOS apps") is left alone. */
function sentenceCase(value: string) {
  if (value !== value.toUpperCase() || value === value.toLowerCase()) return value;
  const lower = value.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

function initialsOf(name: string) {
  // Whitespace only, so an email-derived name like "avery.chen" gives "A", as in the user menu.
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] ?? "S")[0];
  return letters.toUpperCase();
}

function text(value: Value) {
  return typeof value === "string" ? value.trim() : "";
}

function list(value: Value) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string" && item.trim()) : [];
}
