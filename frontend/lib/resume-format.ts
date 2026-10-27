import type { ResumeRecord } from "@/types/api";

type Value = ResumeRecord[string] | undefined;

export function text(value: Value) {
  return typeof value === "string" ? value.trim() : "";
}

export function list(value: Value) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string" && item.trim()) : [];
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2022-03" → "Mar 2022"; "2022" stays; "Present" → "present". */
export function formatMonth(value: string) {
  const match = /^(\d{4})-(\d{2})$/.exec(value);
  const month = match ? MONTHS[Number(match[2]) - 1] : undefined;
  if (match && month) return `${month} ${match[1]}`;
  return value.toLowerCase() === "present" ? "present" : value;
}

/** "Sep 2025 – present", or whichever end is known. */
export function dateRange(record: ResumeRecord) {
  const start = formatMonth(text(record.start_date));
  const end = formatMonth(text(record.end_date));
  return start && end ? `${start} – ${end}` : start || end;
}
