"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Check, FileText, Search, Upload, X } from "lucide-react";

import { ROLE_NAMES } from "@/components/career/route-parts";
import { ResumeAnalysisProgress, type TimedStepEvent } from "@/components/onboarding/resume-analysis-progress";
import { ResumeReview, type Basics } from "@/components/onboarding/resume-review";
import { SetupStepper } from "@/components/setup/setup-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api/client";
import { getMarketDemand } from "@/lib/api/market";
import { addResume, createAccount, getMe, getSavedResume, listDestinations, setDestinationResume, updateAccount } from "@/lib/api/me";
import { streamResumeAnalysis } from "@/lib/api/resumes";
import { acceptedTerms, type SignupMetadata } from "@/lib/auth/account";
import { DEFAULT_UNIVERSITY, EXPERIENCE_LEVELS, RESUME_ACCEPT, RESUME_MAX_BYTES, RESUME_MIME_TYPES, type ExperienceLevel } from "@/lib/options";
import { FAMILY_LABELS, profileForAnalysis, queueSkillGapAnalysis } from "@/lib/skill-gap-profile";
import { text } from "@/lib/resume-format";
import { getSupabase } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import type { JobFamily, MarketDemandSnapshot, ResumeAnalysis, ResumeClassification, SavedResume, User } from "@/types/api";

/** How long the "Found …" summary stays on the progress card before the review opens. */
const AUTO_ADVANCE_MS = 1500;
/** Sent when the location is left empty: the market data isn't filtered by place yet. */
const ANY_LOCATION = "Anywhere";
const FAMILIES: JobFamily[] = ["data_analyst", "software_engineer", "ai_engineer"];

type AnalysisRun = { file: File; events: TimedStepEvent[]; result?: ResumeAnalysis; error?: string };
type Goal = { family: JobFamily | null; level: ExperienceLevel | null; location: string };

/**
 * Setup: 1 upload a résumé, 2 check what was read, 3 choose a target role. The account (or, for a
 * returning student, a new résumé version) is saved only at the end, then the route is calculated.
 * ?step=role (addRole): another destination. The student first picks the saved résumé (then only
 * step 3) or a new one (all three steps).
 */
export function SetupFlow({ graduationYears }: { graduationYears: string[] }) {
  const addRole = useSearchParams().get("step") === "role";
  const [visit, setVisit] = useState(0);
  // The router keeps this page mounted but hidden after leaving it, and runs effect cleanups when it
  // hides it: start over (step, "Saving…", the picked résumé) each time setup is opened again.
  useEffect(() => () => setVisit((count) => count + 1), []);
  return <Steps key={`${visit}:${addRole}`} addRole={addRole} graduationYears={graduationYears} />;
}

function Steps({ addRole, graduationYears }: { addRole: boolean; graduationYears: string[] }) {
  const router = useRouter();
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [file, setFile] = useState<File>();
  const [fileError, setFileError] = useState<string>();
  const [run, setRun] = useState<AnalysisRun>();
  const runController = useRef<AbortController>(null);
  const advanceTimer = useRef<ReturnType<typeof setTimeout>>(null);
  const [analysis, setAnalysis] = useState<ResumeAnalysis>();
  const [classification, setClassification] = useState<ResumeClassification>();
  const [basics, setBasics] = useState<Basics>({ firstName: "", lastName: "", university: "", graduationYear: "" });
  const [reviewError, setReviewError] = useState<string>();
  const [goal, setGoal] = useState<Goal>({ family: null, level: "Internship", location: "" });
  const [account, setAccount] = useState<User | null>(null);
  const [signup, setSignup] = useState<SignupMetadata>();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string>();
  /** addRole: which résumé the new destination uses; null until the student picks. */
  const [resumeChoice, setResumeChoice] = useState<"current" | "new" | null>(null);
  /** addRole: the selected destination's résumé, offered for the new one. */
  const [current, setCurrent] = useState<SavedResume>();
  /** addRole: roles already among the destinations, which can't be added again. */
  const [explored, setExplored] = useState<JobFamily[]>([]);

  // A returning student uploading a new version: start from what the account already has.
  // A new one: from the name and school given at sign-up.
  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => getSupabase().auth.getUser())
      .then(({ data }) => !cancelled && setSignup(data.user?.user_metadata as SignupMetadata | undefined))
      .catch(() => {}); // Supabase isn't configured (UI-only development).
    getMe().then(({ user }) => {
      if (cancelled || !user) return;
      setAccount(user);
      const family = FAMILIES.find((key) => FAMILY_LABELS[key] === user.target_role) ?? null;
      setGoal({ family: addRole ? null : family, level: EXPERIENCE_LEVELS.find((level) => level === user.experience_level) ?? "Internship",
        location: user.preferred_location === ANY_LOCATION ? "" : user.preferred_location });
    }).catch(() => {}); // A new student, or the API is down: start empty.
    if (addRole) {
      getSavedResume().then((saved) => {
        if (cancelled) return;
        if (saved) setCurrent(saved); else setResumeChoice("new");
      }).catch(() => {});
      listDestinations().then((destinations) => !cancelled && setExplored(
        destinations.map((destination) => destination.job_family),
      )).catch(() => {});
    }
    return () => { cancelled = true; };
  }, [addRole]);

  useEffect(() => () => {
    runController.current?.abort();
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
  }, []);

  useEffect(() => { window.scrollTo({ top: 0 }); }, [step]);

  const stopRun = () => {
    runController.current?.abort();
    runController.current = null;
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    advanceTimer.current = null;
  };

  const chooseFile = (next: File | undefined) => {
    setFileError(undefined);
    if (!next) return setFile(undefined);
    if (!RESUME_MIME_TYPES.includes(next.type)) return setFileError("Upload a PDF or DOCX file.");
    if (next.size > RESUME_MAX_BYTES) return setFileError("The file must be 10 MB or smaller.");
    setFile(next);
  };

  const startAnalysis = async (selected: File) => {
    stopRun();
    const controller = new AbortController();
    runController.current = controller;
    setRun({ file: selected, events: [] });
    try {
      const result = await streamResumeAnalysis(selected, (event) => {
        if (controller.signal.aborted) return;
        setRun((current) => current && { ...current, events: [...current.events, { ...event, at: Date.now() }] });
      }, controller.signal);
      if (controller.signal.aborted) return;
      setRun((current) => current && { ...current, result });
      advanceTimer.current = setTimeout(() => {
        setAnalysis(result);
        setClassification(result.classification);
        setBasics(prefillBasics(result.classification, account, signup, graduationYears));
        setRun(undefined);
        setStep(1);
      }, AUTO_ADVANCE_MS);
    } catch (error) {
      if (controller.signal.aborted) return;
      setRun((current) => current && { ...current, error: analysisErrorMessage(error) });
    }
  };

  const continueFromReview = () => {
    const problem = !basics.firstName.trim() || !basics.lastName.trim() ? "Add your first and last name under Basic information."
      : !basics.university.trim() ? "Add your school under Basic information."
      : !basics.graduationYear ? "Choose your graduation year under Basic information." : undefined;
    setReviewError(problem);
    if (!problem) setStep(2);
  };

  const save = async () => {
    if (!goal.family) return setSaveError("Choose a target role.");
    if (!goal.level) return setSaveError("Choose internship or full-time.");
    if (addRole && resumeChoice === "current" && current) return void saveRole(current, goal.family, goal.level);
    if (!analysis || !classification) return;
    const details = { first_name: basics.firstName.trim().slice(0, 100), last_name: basics.lastName.trim().slice(0, 100),
      university: basics.university.trim().slice(0, 150) };
    const goals = { target_role: FAMILY_LABELS[goal.family], experience_level: goal.level,
      graduation_year: Number(basics.graduationYear), preferred_location: goal.location.trim().slice(0, 100) || ANY_LOCATION };
    const resume = { original_filename: analysis.filename, parser: analysis.extraction.parser,
      ocr_pages: analysis.extraction.ocr_pages, agent_name: analysis.agent.name, classification };
    setSaving(true);
    setSaveError(undefined);
    try {
      const { user } = await getMe();
      if (user) {
        // A new résumé for this role (adding the destination if new), now the selected role.
        await Promise.all([updateAccount({ ...details, ...goals }), addResume({ ...resume, job_family: goal.family })]);
      } else {
        // First time: this creates the account, with the terms consent given at sign-up.
        const { data } = await getSupabase().auth.getUser();
        if (!data.user) throw new Error("Not logged in");
        await createAccount({ ...details, ...goals, accept_terms: acceptedTerms(data.user), resume });
      }
    } catch (error) {
      setSaveError(errorMessage(error, "Couldn’t save your profile. Try again."));
      setSaving(false);
      return;
    }
    // Saved first; the route page then analyzes the saved résumé by its id.
    try {
      const [{ user }, saved] = await Promise.all([getMe(), getSavedResume()]);
      if (user && saved) queueSkillGapAnalysis(profileForAnalysis(user, saved));
    } catch { /* Saving succeeded; the analysis can still be started from the route page. */ }
    // A new destination opens on its home page; first-time setup shows the route result first.
    router.push(addRole ? "/dashboard" : "/onboarding/route");
  };

  /** Add a destination that uses the current résumé, and select it. */
  const saveRole = async (source: SavedResume, family: JobFamily, level: ExperienceLevel) => {
    setSaving(true);
    setSaveError(undefined);
    let profile;
    try {
      await setDestinationResume(family, source.id);
      await updateAccount({ target_role: FAMILY_LABELS[family], experience_level: level,
        preferred_location: goal.location.trim().slice(0, 100) || ANY_LOCATION });
      const [{ user }, saved] = await Promise.all([getMe(), getSavedResume()]);
      if (!user || !saved) throw new Error("Upload your résumé first.");
      profile = profileForAnalysis(user, saved);
    } catch (error) {
      setSaveError(errorMessage(error, "Couldn’t save your target role. Try again."));
      setSaving(false);
      return;
    }
    queueSkillGapAnalysis(profile);
    router.push("/dashboard");
  };

  if (addRole && resumeChoice === null) {
    return <Frame>
      <h1 className="text-page-title">Add a destination</h1>
      <p className="mt-2 text-base/7 text-muted-foreground">Which résumé should we compare with the new role?</p>
      <div className="mt-8 grid gap-3">
        <ChoiceCard icon={FileText} title="Use my current résumé" detail={current?.original_filename ?? "Loading…"} disabled={!current}
          onClick={() => setResumeChoice("current")} />
        <ChoiceCard icon={Upload} title="Upload a new résumé" detail="Used only for the role you choose next"
          onClick={() => setResumeChoice("new")} />
      </div>
      <div className="mt-8"><Button type="button" variant="ghost" size="lg" onClick={() => router.push("/destinations")}>Back</Button></div>
    </Frame>;
  }

  if (addRole && resumeChoice === "current") {
    return <Frame wide>
      <RoleStep goal={goal} onChange={setGoal} saving={saving} error={saveError} explored={explored}
        title="Add a destination" description="We’ll compare your current résumé with real job postings for this role. Location is optional."
        onBack={() => setResumeChoice(null)} onSubmit={() => void save()} />
    </Frame>;
  }

  if (step === 1 && analysis && classification) {
    return <Frame step={1} wide>
      <ResumeReview result={analysis} classification={classification} onChange={setClassification}
        basics={basics} onBasicsChange={setBasics} graduationYears={graduationYears} error={reviewError}
        onBack={() => setStep(0)} onContinue={continueFromReview} />
    </Frame>;
  }

  if (step === 2) {
    return <Frame step={2} wide>
      <RoleStep goal={goal} onChange={setGoal} saving={saving} error={saveError} explored={addRole ? explored : []}
        onBack={() => setStep(1)} onSubmit={() => void save()} />
    </Frame>;
  }

  return (
    <Frame step={0}>
      <div className="text-center">
        <h1 className="text-page-title">Upload your résumé</h1>
        <p className="mx-auto mt-3 max-w-xl text-lg/8 text-muted-foreground">
          We’ll read your skills and experience from it. You’ll check everything on the next step.
        </p>
      </div>
      {run ? (
        <div className="mt-10">
          <ResumeAnalysisProgress file={run.file} events={run.events} result={run.result} error={run.error}
            onCancel={() => { stopRun(); setRun(undefined); }}
            onRetry={() => void startAnalysis(run.file)}
            onChooseAnotherFile={() => { stopRun(); setRun(undefined); setFile(undefined); }} />
        </div>
      ) : <>
        <Dropzone onFile={chooseFile} />
        {fileError && <p role="alert" className="mt-3 text-center text-destructive">{fileError}</p>}
        {file && (
          <div className="mt-6 flex items-center gap-4 rounded-xl border border-border bg-card px-5 py-4">
            <FileText aria-hidden className="size-5 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-bold">{file.name}</p>
              <p className="font-mono text-sm text-muted-foreground">{formatBytes(file.size)}</p>
            </div>
            <span className="hidden items-center gap-1 text-sm font-bold text-success sm:inline-flex"><Check aria-hidden className="size-4" />Ready</span>
            <Button variant="ghost" size="icon-sm" aria-label={`Remove ${file.name}`} onClick={() => setFile(undefined)}><X /></Button>
          </div>
        )}
        {analysis && classification && !file && (
          <p className="mt-6 text-center text-muted-foreground">
            Or <button type="button" className="font-bold text-foreground underline" onClick={() => setStep(1)}>go back to {analysis.filename}</button>
          </p>
        )}
        <div className="mt-10 grid justify-items-center gap-3">
          <Button size="lg" disabled={!file} onClick={() => file && void startAnalysis(file)}>Continue<ArrowRight data-icon="inline-end" /></Button>
          <p className="text-sm text-muted-foreground">Only you can see your résumé.</p>
          {addRole && <Button type="button" variant="ghost" onClick={() => { setFile(undefined); setResumeChoice(null); }}>Back</Button>}
        </div>
      </>}
    </Frame>
  );
}

function Frame({ step, wide = false, children }: { step?: 0 | 1 | 2; wide?: boolean; children: React.ReactNode }) {
  return (
    <div className={cn("mx-auto w-full px-4 pt-10 pb-20 sm:px-6", wide ? "max-w-232" : "max-w-166")}>
      {step !== undefined && <SetupStepper current={step} className="mb-10" />}
      {children}
    </div>
  );
}

function ChoiceCard({ icon: Icon, title, detail, disabled = false, onClick }: {
  icon: typeof FileText; title: string; detail: string; disabled?: boolean; onClick: () => void;
}) {
  return (
    <button type="button" disabled={disabled} onClick={onClick}
      className="flex items-center gap-4 rounded-2xl border border-border bg-card px-5 py-4 text-left transition-colors hover:bg-background disabled:opacity-60">
      <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-full bg-accent"><Icon className="size-5" /></span>
      <span className="min-w-0 flex-1">
        <span className="block text-title">{title}</span>
        <span className="block truncate text-sm text-muted-foreground">{detail}</span>
      </span>
      <ArrowRight aria-hidden className="size-5 shrink-0" />
    </button>
  );
}

function Dropzone({ onFile }: { onFile: (file: File | undefined) => void }) {
  const [dragging, setDragging] = useState(false);
  return (
    <label
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => { event.preventDefault(); setDragging(false); onFile(event.dataTransfer.files[0]); }}
      className={cn("mt-10 grid cursor-pointer justify-items-center gap-2 rounded-2xl border border-dashed border-line-strong bg-card px-6 py-12 text-center transition-colors hover:bg-background has-focus-visible:ring-3 has-focus-visible:ring-ring/30",
        dragging && "bg-accent/30")}>
      <span aria-hidden className="mb-2 grid size-16 place-items-center rounded-full bg-accent"><Upload className="size-6" /></span>
      <span className="text-title">Drop your résumé here</span>
      <span className="text-sm text-muted-foreground">PDF or DOCX, up to 10 MB</span>
      <span className="mt-3 inline-flex h-11 items-center rounded-full border border-line-strong bg-card px-5 font-bold">Choose a file</span>
      <input type="file" accept={RESUME_ACCEPT} className="sr-only" onChange={(event) => { onFile(event.target.files?.[0]); event.target.value = ""; }} />
    </label>
  );
}

function RoleStep({ goal, onChange, saving, error, explored = [], title = "Choose a target role",
  description = "We’ll compare your résumé with real job postings for this role. Location is optional.", onBack, onSubmit }: {
  goal: Goal; onChange: (goal: Goal) => void; saving: boolean; error?: string; explored?: JobFamily[];
  title?: string; description?: string; onBack: () => void; onSubmit: () => void;
}) {
  const [query, setQuery] = useState("");
  const [markets, setMarkets] = useState<Partial<Record<JobFamily, MarketDemandSnapshot | null>>>({});
  useEffect(() => {
    let active = true;
    for (const key of FAMILIES) {
      getMarketDemand(key)
        .then((data) => active && setMarkets((current) => ({ ...current, [key]: data })))
        .catch(() => active && setMarkets((current) => ({ ...current, [key]: null })));
    }
    return () => { active = false; };
  }, []);
  const matches = FAMILIES.filter((key) => ROLE_NAMES[key].toLowerCase().includes(query.trim().toLowerCase()));
  const largest = FAMILIES.reduce<JobFamily | null>((best, key) =>
    (markets[key]?.sample_size ?? 0) > (best ? markets[best]?.sample_size ?? 0 : 0) ? key : best, null);

  return (
    <form noValidate onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
      <h1 className="text-page-title">{title}</h1>
      <p className="mt-2 text-base/7 text-muted-foreground">{description}</p>

      <label htmlFor="role-search" className="mt-8 block text-sm font-bold">Target role</label>
      <div className="relative mt-2">
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-4 size-4.5 -translate-y-1/2 text-muted-foreground" />
        <Input id="role-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search roles" className="pl-11" />
      </div>
      <p className="mt-5 mb-3 text-sm font-bold" aria-live="polite">
        {query.trim() ? `${matches.length} ${matches.length === 1 ? "role matches" : "roles match"} “${query.trim()}”` : `${FAMILIES.length} roles available`}
      </p>
      <div role="radiogroup" aria-label="Target role" className="grid gap-3">
        {matches.map((key) => {
          const market = markets[key];
          const selected = goal.family === key;
          const added = explored.includes(key);
          return (
            <button key={key} type="button" role="radio" aria-checked={selected} disabled={added} onClick={() => onChange({ ...goal, family: key })}
              className={cn("flex items-center gap-4 rounded-2xl border border-border bg-card px-5 py-4 text-left transition-colors hover:bg-background disabled:opacity-60 disabled:hover:bg-card",
                selected && "border-2 border-foreground px-[1.1875rem] py-[0.9375rem]")}>
              <span aria-hidden className={cn("grid size-5 shrink-0 place-items-center rounded-full border-2", selected ? "border-foreground" : "border-line-strong")}>
                {selected && <span className="size-2.5 rounded-full bg-foreground" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-title">{ROLE_NAMES[key]}</span>
                <span className="block font-mono text-sm text-muted-foreground">
                  {added ? "Already in your destinations" : market === undefined ? "Loading…" : market === null ? "Market data unavailable"
                    : `${market.sample_size.toLocaleString()} postings analyzed · ${market.core_skill_count} core skills`}
                </span>
              </span>
              {key === largest && <Badge variant="warning" className="hidden sm:inline-flex">Most postings</Badge>}
            </button>
          );
        })}
        {matches.length === 0 && <p className="text-muted-foreground">We don’t cover that role yet. We support data analyst, software engineer and AI engineer.</p>}
      </div>

      <div className="mt-8 grid gap-6 sm:grid-cols-2">
        <div>
          <p id="level-label" className="text-sm font-bold">Looking for</p>
          <div role="radiogroup" aria-labelledby="level-label" className="mt-2 flex rounded-full bg-sunken p-1">
            {EXPERIENCE_LEVELS.map((level) => (
              <button key={level} type="button" role="radio" aria-checked={goal.level === level} onClick={() => onChange({ ...goal, level })}
                className={cn("h-10 flex-1 rounded-full font-bold text-muted-foreground", goal.level === level && "bg-card text-foreground shadow-card")}>
                {level}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label htmlFor="location" className="text-sm font-bold">Location <span className="font-normal text-muted-foreground">(optional)</span></label>
          <Input id="location" value={goal.location} maxLength={100} placeholder="Anywhere" autoComplete="address-level2"
            onChange={(event) => onChange({ ...goal, location: event.target.value })} className="mt-2" />
        </div>
      </div>

      {error && <p role="alert" className="mt-6 text-destructive">{error}</p>}
      <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-6">
        <Button type="button" variant="ghost" size="lg" onClick={onBack}>Back</Button>
        <Button type="submit" size="lg" disabled={saving}>{saving ? "Saving…" : "Calculate my route"}<ArrowRight data-icon="inline-end" /></Button>
      </div>
    </form>
  );
}

function prefillBasics(classification: ResumeClassification, account: User | null,
  signup: SignupMetadata | undefined, years: string[]): Basics {
  const name = signup?.full_name?.trim() || text(classification.personal_information.name);
  const [first = "", ...rest] = name.split(/\s+/).filter(Boolean);
  const school = classification.education.map((entry) => text(entry.institution)).find(Boolean);
  const endYear = classification.education.map((entry) => /\d{4}/.exec(text(entry.end_date))?.[0]).find(Boolean);
  const accountYear = account ? String(account.graduation_year) : undefined;
  return {
    firstName: account?.first_name ?? first,
    lastName: account?.last_name ?? rest.join(" "),
    // Returning: the new résumé's school, else the saved one. New: the school given at sign-up first.
    university: ((account ? school || account.university : signup?.university || school) || DEFAULT_UNIVERSITY).slice(0, 150),
    graduationYear: [accountYear, endYear].find((year) => year && years.includes(year)) ?? "",
  };
}

/** The backend's own explanation when it gave one; friendlier text for "unreachable" and "logged out". */
function analysisErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong while reading the résumé.";
  if (error.status === 0 || error.status === 401) return errorMessage(error);
  return error.detail ?? error.message;
}

function formatBytes(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
