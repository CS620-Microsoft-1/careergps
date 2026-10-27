"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BookOpen, Briefcase, Check, FileText, GraduationCap, LoaderCircle, Plus, Upload, Users } from "lucide-react";

import { ROLE_NAMES, skillLabel } from "@/components/career/route-parts";
import { useAccount } from "@/components/layout/account-provider";
import { BackendStatus } from "@/components/layout/backend-status";
import { usePlan } from "@/components/plan/plan-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api/client";
import { getSavedResume, listResumes, setDestinationResume } from "@/lib/api/me";
import { EVIDENCE_LABELS, evidenceLevel, rankGaps, rankStrengths } from "@/lib/career";
import { EXPERIENCE_LEVELS } from "@/lib/options";
import { dateRange, list, text } from "@/lib/resume-format";
import type { ResumeClassification, ResumeSummary, SavedResume } from "@/types/api";

type Library = { status: "loading" | "ready" | "error"; versions: ResumeSummary[]; active: SavedResume | null };

export function ProfileView() {
  const { user, email, displayName, initials, status } = useAccount();
  const [library, setLibrary] = useState<Library>({ status: "loading", versions: [], active: null });

  useEffect(() => {
    let cancelled = false;
    Promise.all([listResumes(), getSavedResume()])
      .then(([versions, active]) => !cancelled && setLibrary({ status: "ready", versions, active }))
      .catch(() => !cancelled && setLibrary({ status: "error", versions: [], active: null }));
    return () => { cancelled = true; };
  }, []);

  const classification = library.active?.classification;
  const major = classification?.education.map((e) => text(e.major)).find(Boolean);

  return <>
    <div className="mb-8 flex flex-wrap items-center gap-5">
      <span aria-hidden className="grid size-18 shrink-0 place-items-center rounded-full bg-tint-blue text-2xl font-extrabold">{initials}</span>
      <div className="min-w-0">
        <p className="eyebrow">Profile · your start</p>
        <h1 className="mt-1 text-page-title">{displayName || (status === "loading" ? "Loading…" : "Your profile")}</h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <span className="font-mono text-sm text-muted-foreground">
            {[major, user && `Class of ${user.graduation_year}`].filter(Boolean).join(" · ")}
          </span>
          {user?.university && <span className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-3 py-0.5 text-sm font-bold">
            <GraduationCap aria-hidden className="size-4" />{user.university}</span>}
        </div>
      </div>
    </div>

    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <div className="grid gap-6">
        <ResumeLibrary library={library} />
        <Skills classification={classification} />
        {classification && <Experience classification={classification} />}
      </div>
      <aside className="grid gap-5">
        <SchoolCard email={email} />
        <GoalCard />
        <section className="rounded-2xl bg-sunken p-6">
          <h2 className="text-title">Your data</h2>
          <p className="mt-2 text-sm/6 text-muted-foreground">Only you can see your résumés. We keep each version you confirm so you can go back to it.</p>
          <BackendStatus className="mt-4" />
        </section>
      </aside>
    </div>
  </>;
}

function ResumeLibrary({ library }: { library: Library }) {
  const { family } = useSkillGapAnalysis();
  const [switching, setSwitching] = useState<string>();
  const [error, setError] = useState<string>();
  const role = ROLE_NAMES[family];
  const use = async (id: string) => {
    setSwitching(id);
    setError(undefined);
    try {
      await setDestinationResume(family, id);
      // The analysis, plan and nav bar all follow the selected destination's résumé: start them fresh.
      window.location.reload();
    } catch (failure) {
      setError(errorMessage(failure, "Couldn’t switch résumés. Try again."));
      setSwitching(undefined);
    }
  };
  return (
    <section aria-labelledby="resumes" className="rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8">
      <h2 id="resumes" className="text-section">Résumé library</h2>
      <p className="mt-1 text-sm/6 text-muted-foreground">Each destination is matched against one résumé, and roles can share one. Switching the résumé for {role.toLowerCase()} recalculates only that route.</p>
      {library.status === "loading" ? <p className="mt-4 text-muted-foreground">Loading your résumés…</p>
        : library.status === "error" ? <p role="alert" className="mt-4 text-destructive">Your résumés could not be loaded.</p>
        : <ul className="mt-5 grid gap-3">
          {library.versions.map((version) => {
            const selected = version.destinations.includes(family);
            return (
              <li key={version.id} className="flex flex-wrap items-center gap-4 rounded-xl bg-sunken px-5 py-4">
                <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-full bg-card"><FileText className="size-4.5" /></span>
                <div className="min-w-0 flex-1 basis-48">
                  <p className="truncate font-bold">{version.label ?? version.original_filename}</p>
                  <p className="text-sm text-muted-foreground">
                    Confirmed {formatDate(version.created_at)} · {version.destinations.length
                      ? `used for ${version.destinations.map((key) => ROLE_NAMES[key].toLowerCase()).join(", ")}` : "not in use"}
                  </p>
                </div>
                {selected ? <Badge variant="brand">In use</Badge>
                  : <Button variant="outline" disabled={Boolean(switching)} onClick={() => void use(version.id)}>
                    {switching === version.id && <LoaderCircle data-icon="inline-start" className="motion-safe:animate-spin" />}Use for {role.toLowerCase()}
                  </Button>}
              </li>
            );
          })}
        </ul>}
      {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
      <Link href="/onboarding" className="mt-4 flex h-14 items-center justify-center gap-2 rounded-xl border border-dashed border-line-strong font-bold hover:bg-background">
        <Upload aria-hidden className="size-4.5" />Upload a résumé version
      </Link>
    </section>
  );
}

function Skills({ classification }: { classification?: ResumeClassification }) {
  const { run } = useSkillGapAnalysis();
  const [all, setAll] = useState(false);
  const report = run?.status === "completed" ? run.report : null;
  const strengths = report ? rankStrengths(report) : [];
  const building = report ? rankGaps(report).slice(0, 6) : [];
  const listed = classification?.technical_skills.filter((skill) => skill.trim()) ?? [];
  const shown = all ? strengths : strengths.slice(0, 6);
  return (
    <section aria-labelledby="skills" className="rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8">
      <h2 id="skills" className="text-section">Skills</h2>
      {report ? <>
        <p className="eyebrow mt-5 mb-2">Strengths · {strengths.length}</p>
        {strengths.length ? <ul className="flex flex-wrap gap-2">
          {shown.map((skill) => <li key={skill.skill_id} className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-3 py-1 text-sm font-semibold">
            <Check aria-hidden className="size-3.5" />{skillLabel(skill.skill_id)}</li>)}
          {strengths.length > 6 && <li><button type="button" onClick={() => setAll(!all)} className="rounded-full bg-sunken px-3 py-1 text-sm font-semibold">
            {all ? "Show fewer" : `+${strengths.length - 6} more`}</button></li>}
        </ul> : <p className="text-sm text-muted-foreground">None yet for this destination.</p>}
        <p className="eyebrow mt-5 mb-2">Building now</p>
        <ul className="flex flex-wrap gap-2">
          {building.map((skill) => <li key={skill.skill_id} className="rounded-full bg-sunken px-3 py-1 text-sm font-semibold">
            {skillLabel(skill.skill_id)} · {EVIDENCE_LABELS[evidenceLevel(skill.resume_evidence_strength ?? 0)]}</li>)}
        </ul>
      </> : <p className="mt-2 text-sm text-muted-foreground">Strengths and gaps appear once your route is calculated.</p>}
      {listed.length > 0 && <>
        <p className="eyebrow mt-5 mb-2">On your résumé · {listed.length}</p>
        <ul className="flex flex-wrap gap-2">
          {listed.map((skill, index) => <li key={`${skill}-${index}`} className="rounded-full border border-border px-3 py-1 text-sm">{skill}</li>)}
        </ul>
      </>}
      <Link href="/onboarding" className="mt-5 inline-block font-bold underline">Edit skills in a new résumé version</Link>
    </section>
  );
}

function Experience({ classification: c }: { classification: ResumeClassification }) {
  const entries = [
    ...c.work_experience.map((r) => ({ icon: Briefcase, title: r.title, org: r.company, record: r })),
    ...c.research_experience.map((r) => ({ icon: BookOpen, title: r.title, org: r.organization, record: r })),
    ...c.leadership_activities.map((r) => ({ icon: Users, title: r.role, org: r.organization, record: r })),
  ];
  return (
    <section aria-labelledby="exp" className="rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8">
      <h2 id="exp" className="text-section">Experience</h2>
      {entries.length ? <ul className="mt-5 grid gap-5">
        {entries.map(({ icon: Icon, title, org, record }, index) => (
          <li key={index} className="flex gap-4">
            <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-full bg-sunken"><Icon className="size-4.5" /></span>
            <div className="min-w-0">
              <p className="font-bold">{text(title) || text(org) || "Untitled"}</p>
              <p className="text-sm text-muted-foreground">{[text(title) ? text(org) : "", dateRange(record)].filter(Boolean).join(" · ")}</p>
              {list(record.content)[0] && <p className="mt-1 text-sm/6 text-muted-foreground">{list(record.content)[0]}</p>}
            </div>
          </li>
        ))}
      </ul> : <p className="mt-2 text-sm text-muted-foreground">No experience on this résumé yet.</p>}
      <Link href="/onboarding" className="mt-5 inline-flex items-center gap-1.5 font-bold hover:underline"><Plus aria-hidden className="size-4.5" />Add experience</Link>
    </section>
  );
}

function SchoolCard({ email }: { email: string | null }) {
  const { user, update } = useAccount();
  const plan = usePlan();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [state, setState] = useState<{ saving: boolean; error?: string }>({ saving: false });
  const campus = plan.resources.some((resource) => resource.school);
  const save = async () => {
    if (!value.trim()) return setState({ saving: false, error: "Enter your school." });
    setState({ saving: true });
    try {
      await update({ university: value.trim() });
      // Campus resources follow the school: reload them with the new one.
      window.location.reload();
    } catch (error) {
      setState({ saving: false, error: errorMessage(error, "Couldn’t save your school.") });
    }
  };
  return (
    <section aria-labelledby="school" className="rounded-2xl border border-border bg-card p-6 shadow-card">
      <h2 id="school" className="text-title">School</h2>
      <div className="mt-3 flex gap-3">
        <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-full bg-success-soft"><GraduationCap className="size-4.5" /></span>
        <div className="min-w-0">
          <p className="font-bold">{user?.university ?? "—"}</p>
          {email && <p className="text-sm break-all text-muted-foreground">Signed in as {email}</p>}
        </div>
      </div>
      <p className="mt-3 text-sm/6 text-muted-foreground">{campus ? "Your resources include courses and student orgs on your campus."
        : "We don’t have campus courses and clubs for this school yet."}</p>
      {editing ? <form className="mt-3 grid gap-2" onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <label htmlFor="school-name" className="text-sm font-bold">School name</label>
        <Input id="school-name" value={value} maxLength={150} onChange={(event) => setValue(event.target.value)} autoComplete="organization" />
        {state.error && <p role="alert" className="text-sm text-destructive">{state.error}</p>}
        <div className="flex gap-2">
          <Button type="submit" size="sm" disabled={state.saving}>{state.saving ? "Saving…" : "Save"}</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
        </div>
      </form> : <button type="button" onClick={() => { setValue(user?.university ?? ""); setEditing(true); }}
        className="mt-3 font-bold hover:underline">Change school</button>}
    </section>
  );
}

function GoalCard() {
  const { user, update } = useAccount();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ location: "", level: "" });
  const [state, setState] = useState<{ saving: boolean; error?: string }>({ saving: false });
  if (!user) return null;
  const save = async () => {
    if (!draft.location.trim()) return setState({ saving: false, error: "Enter a location, or “Anywhere”." });
    setState({ saving: true });
    try {
      await update({ preferred_location: draft.location.trim(), experience_level: draft.level });
      setEditing(false);
      setState({ saving: false });
    } catch (error) {
      setState({ saving: false, error: errorMessage(error, "Couldn’t save your goal.") });
    }
  };
  return (
    <section aria-labelledby="goal" className="rounded-2xl border border-border bg-card p-6 shadow-card">
      <h2 id="goal" className="text-title">Looking for</h2>
      {editing ? <form className="mt-3 grid gap-3" onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <div role="radiogroup" aria-label="Job type" className="flex rounded-full bg-sunken p-1">
          {EXPERIENCE_LEVELS.map((level) => <button key={level} type="button" role="radio" aria-checked={draft.level === level}
            onClick={() => setDraft({ ...draft, level })}
            className={`h-9 flex-1 rounded-full text-sm font-bold ${draft.level === level ? "bg-card shadow-card" : "text-muted-foreground"}`}>{level}</button>)}
        </div>
        <label htmlFor="goal-location" className="text-sm font-bold">Location</label>
        <Input id="goal-location" value={draft.location} maxLength={100} onChange={(event) => setDraft({ ...draft, location: event.target.value })} />
        {state.error && <p role="alert" className="text-sm text-destructive">{state.error}</p>}
        <div className="flex gap-2">
          <Button type="submit" size="sm" disabled={state.saving}>{state.saving ? "Saving…" : "Save"}</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
        </div>
      </form> : <>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-muted-foreground">Type</dt><dd className="font-bold">{user.experience_level}</dd>
          <dt className="text-muted-foreground">Where</dt><dd className="font-bold">{user.preferred_location}</dd>
          <dt className="text-muted-foreground">Graduating</dt><dd className="font-bold">{user.graduation_year}</dd>
        </dl>
        <button type="button" onClick={() => { setDraft({ location: user.preferred_location, level: user.experience_level }); setEditing(true); }}
          className="mt-3 font-bold hover:underline">Edit</button>
      </>}
    </section>
  );
}

function formatDate(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "earlier" : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
