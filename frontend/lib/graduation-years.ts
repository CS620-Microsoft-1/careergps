import { cacheLife } from "next/cache";

/**
 * This year plus the next four, as strings for <select> values.
 * Pages are prerendered, so the current year is read inside a cached scope
 * (refreshed daily) instead of during render.
 */
export async function getGraduationYears(): Promise<string[]> {
  "use cache";
  cacheLife("days");
  const year = new Date().getFullYear();
  return Array.from({ length: 5 }, (_, i) => String(year + i));
}
