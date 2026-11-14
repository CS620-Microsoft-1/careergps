// Résumé course suggestions the student answered "Not now" to. Kept in this browser, one list per
// account, so another student who signs in here is still asked. Free of runtime imports for node --test.

const PREFIX = "careergps:resume-course-matches:dismissed";

export function dismissedKey(userId: string): string {
  return `${PREFIX}:${userId}`;
}

/** Course ids this account said "Not now" to, in this browser. */
export function readDismissed(userId: string): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(dismissedKey(userId)) ?? "[]");
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

export function writeDismissed(userId: string, ids: string[]): void {
  try {
    localStorage.setItem(dismissedKey(userId), JSON.stringify(ids));
  } catch {
    // Private mode or blocked storage: the prompt just comes back next time.
  }
}
