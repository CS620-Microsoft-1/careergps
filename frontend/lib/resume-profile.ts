import { FAMILY_LABELS, type ConfirmedResumeSnapshot } from "@/lib/confirmed-resume";

export type ResumeProfile = {
  name: string;
  initials: string;
  institution: string | null;
  subtitle: string;
  graduationYear: string | null;
  targetRole: string | null;
  filename: string | null;
};

function text(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value.trim().replace(/\s+/gu, " ");
  return cleaned || null;
}

function educationDate(value: unknown): number | null {
  const match = text(value)?.match(/^(\d{4})(?:-(0[1-9]|1[0-2]))?(?:-\d{2})?$/u);
  return match ? Number(match[1]) * 12 + Number(match[2] ?? 1) : null;
}

function institutionFrom(education: unknown): string | null {
  let selected: string | null = null;
  let latest = -Infinity;
  if (!Array.isArray(education)) return null;
  for (const record of education) {
    if (record === null || typeof record !== "object") continue;
    const institution = text(record.institution);
    if (!institution) continue;
    const date = educationDate(record.start_date) ?? educationDate(record.end_date) ?? -Infinity;
    if (selected === null || date > latest) {
      selected = institution;
      latest = date;
    }
  }
  return selected;
}

function initialsFrom(name: string): string {
  const words = name.split(/\s+/u);
  const first = Array.from(words[0])[0] ?? "S";
  const last = words.length > 1 ? Array.from(words[words.length - 1])[0] ?? "" : "";
  return (first + last).toLocaleUpperCase();
}

/** Display only the user-confirmed profile; no inferred identity or account state. */
export function getResumeProfile(snapshot: ConfirmedResumeSnapshot | null): ResumeProfile {
  if (!snapshot) return {
    name: "Student", initials: "S", institution: null, subtitle: "Résumé not confirmed",
    graduationYear: null, targetRole: null, filename: null,
  };
  const personal = snapshot.reviewed_resume?.personal_information;
  const name = text(personal?.name) ?? text(personal?.full_name) ?? "Student";
  const institution = institutionFrom(snapshot.reviewed_resume?.education);
  const targetRole = FAMILY_LABELS[snapshot.job_family] ?? null;
  return {
    name,
    initials: initialsFrom(name),
    institution,
    subtitle: institution ?? targetRole ?? "Reviewed résumé",
    graduationYear: text(snapshot.onboarding?.graduationYear),
    targetRole,
    filename: text(snapshot.filename),
  };
}
