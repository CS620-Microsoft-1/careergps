// Where to send the user after logging in: the page they were on before /login.

const AUTH_PATHS = ["/login", "/signup", "/auth"];

/**
 * The `next` value if it is a path on this site, otherwise null. Rejects absolute URLs and
 * protocol-relative ones ("//evil.example", "/\evil.example") so /login can't be used to
 * send people to another site, and auth pages so login can't loop back to itself.
 */
export function safeNextPath(raw: string | string[] | null | undefined): string | null {
  if (typeof raw !== "string") return null;
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return null;
  if (/[\u0000-\u001f\\]/.test(raw)) return null;
  const pathname = raw.split(/[?#]/)[0];
  if (AUTH_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))) return null;
  return raw;
}

/** /login, remembering the current page when it is one worth returning to. */
export function loginPath(current: string): string {
  const next = safeNextPath(current);
  return next && next !== "/" ? `/login?next=${encodeURIComponent(next)}` : "/login";
}
