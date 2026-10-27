import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { loginPath, safeNextPath } from "@/lib/auth/next-path";
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/supabase/config";

// Pages that need a logged-in user. Everything else is public.
const PROTECTED_PREFIXES = [
  "/dashboard",
  "/destinations",
  "/gaps",
  "/onboarding",
  "/plan",
  "/profile",
  "/resources",
];
const AUTH_PAGES = ["/login", "/signup"];

const startsWithAny = (path: string, prefixes: string[]) =>
  prefixes.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));

/**
 * Refreshes the Supabase session cookies on every page request and sends people to the
 * right place: logged out → /login (remembering the page in ?next=), logged in → away from
 * /login and /signup.
 * This only checks the session; the API checks the token again on every call.
 */
export async function proxy(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;

  // A confirmation link that lands on / (e.g. a template without the /auth/confirm path):
  // pass its token_hash on to /auth/confirm.
  if (pathname === "/" && searchParams.has("token_hash")) {
    const url = request.nextUrl.clone();
    url.pathname = "/auth/confirm";
    return NextResponse.redirect(url);
  }

  let response = NextResponse.next({ request });
  if (!SUPABASE_URL || !SUPABASE_PUBLISHABLE_KEY) return response;

  const supabase = createServerClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll(cookiesToSet, headers) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
        Object.entries(headers).forEach(([key, value]) => response.headers.set(key, value));
      },
    },
  });

  // getClaims verifies the token's signature (Supabase's public keys), unlike getSession.
  const { data } = await supabase.auth.getClaims();
  const loggedIn = Boolean(data?.claims);

  // path may carry its own query, e.g. /login?next=%2Fprofile.
  const redirectTo = (path: string) => {
    const url = new URL(path, request.nextUrl);
    const redirect = NextResponse.redirect(url);
    // Keep any refreshed session cookies.
    response.cookies.getAll().forEach((cookie) => redirect.cookies.set(cookie));
    return redirect;
  };

  if (pathname === "/") return redirectTo(loggedIn ? "/dashboard" : "/login");
  if (!loggedIn && startsWithAny(pathname, PROTECTED_PREFIXES)) {
    return redirectTo(loginPath(pathname + request.nextUrl.search));
  }
  if (loggedIn && startsWithAny(pathname, AUTH_PAGES)) {
    return redirectTo(safeNextPath(searchParams.get("next")) ?? "/dashboard");
  }

  return response;
}

export const config = {
  // Pages only: skip Next.js internals and static files.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
