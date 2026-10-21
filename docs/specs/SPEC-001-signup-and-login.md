# SPEC-001: Sign up and log in

- **Status:** Draft
- **Date:** 2026-10-10 (narrowed to auth on 2026-10-14)
- **Scope:** Account creation with Supabase Auth, creating the `users` row at the end of onboarding, verifying login tokens in FastAPI
- **Related:** [ADR-001](../decisions/ADR-001-CareerGPS-Frontend.md), [ADR-002](../decisions/ADR-002-CareerGPS-Backend.md), [Supabase test plan](../testing/SUPABASE_DATABASE_TEST_PLAN.md)

Items marked **[DECIDED]** were settled by the team. Priorities (P0 / P1 / P2) are listed in §3.

Résumé upload and parsing are not part of this spec: they are built in PR #11 (`POST /resumes/analyze`).

---

## 1. Goal

A new student can create an account with email and password, confirm their email, and log in. The backend knows who is calling every endpoint. Sign-up asks only for email and password; the `users` row (career goal, name, first résumé) is created when onboarding is confirmed (schema: PR #17, `backend/app/models/user.py`).

## 2. Current state (as of `dev` @ `75ea4d2`)

| Area | What exists |
|---|---|
| Frontend | `/signup`, `/login`, `/onboarding`, `/dashboard` screens. The sign-up and login forms validate with zod (`frontend/lib/validation/auth.ts`) and then just `router.push` to the next page. No Supabase calls yet. |
| Signup form | full name, email, password (8–128), confirm password, target role, graduation year, university, experience level, accept terms |
| Backend | FastAPI app with `/health`, `/health/db` and `POST /resumes/analyze`. No authentication. |
| Database | `users` (id, email, full_name, created_at, updated_at), RLS enabled, no policies. The backend connects as `postgres` and bypasses RLS. |
| CI | Baseline checks run on every PR to `dev` (`backend/tests/test_baseline_configuration.py`). They assert that `users.email` is unique and **not nullable**. |

## 3. Priorities

- **P0**: the first release.
- **P1**: the next release, right after P0.
- **P2**: later.

### P0

| # | Task | Basis |
|---|---|---|
| P0-1 | Sign up with **email** + password, using **Supabase Auth**, with **email confirmation on** (§6) | Decided |
| P0-2 | Log in, log out, session via Supabase Auth; FastAPI verifies the Supabase JWT (§6) | Decided |
| P0-3 | Create the `users` row and the first `resumes` row when onboarding is confirmed (`POST /me`, records the terms consent). Name and university are confirmed in onboarding (the university is pre-filled from the résumé) | Decided |
| P0-4 | Route guard: not logged in → `/login` | Decided |
| P0-5 | Sign-up asks only for **email, password (typed twice) and the terms checkbox**. Name and career goal (target role, graduation year, experience level) are asked in onboarding; the university is pre-filled from the résumé on the review page | Decided |
| P0-6 | Rate limit sign-up and login (Supabase Auth's built-in limits, configured in the dashboard) | Decided |
| P0-7 | Security checklist (§8) and tests (§9) | Decided |

### P1

| # | Task | Basis |
|---|---|---|
| P1-1 | Password reset by email (Supabase Auth built-in; needs custom SMTP) | Decided |
| P1-2 | Custom SMTP so confirmation and reset emails reach real users | Proposed |

### P2

| # | Task | Basis |
|---|---|---|
| P2-1 | SSO login via Supabase Auth OAuth providers. The buttons are removed from the P0 login page; `components/auth/sso-buttons.tsx` is kept for this | Proposed |
| P2-2 | Route guard: onboarding not finished (no `users` row) → `/onboarding`. Done in the app shell (`components/layout/onboarding-guard.tsx`) | Done |

## 4. Flow

```text
/signup ──supabase.auth.signUp()──▶ Supabase Auth creates the account and emails a confirmation link
   │                                  (terms consent saved in user_metadata)
   │
confirmation link ──▶ /auth/confirm ──▶ session created
   ▼
/onboarding ──POST /resumes/analyze──▶ classification to review
            ──POST /me (Bearer JWT)──▶ users row + first résumé created (terms consent from user_metadata)
later, from /profile: /onboarding ──PATCH /me + POST /me/resumes──▶ goal updated, new résumé version active
```

## 5. Data model

All tables get RLS enabled with no policies, as with `users` (the backend is the only client). All new migrations are additive.

Migrations follow the shared database rules in `backend/README.md`: generated with Alembic and reviewed in the PR, never created in the Supabase dashboard, applied from `dev` after the PR is merged, by one person who announces it in the team chat, and `ENABLE ROW LEVEL SECURITY` in every new table's migration.

### 5.1 `users` and résumé tables

**[DECIDED] Users sign up and log in with email + password through Supabase Auth.** Supabase keeps accounts and password hashes in its own `auth.users` table; our database never stores passwords.

The tables are defined by PR #17 (migration `02a858fed0df`; see `backend/README.md`, "Users and résumé tables"). What this spec relies on:

| Column / table | Notes |
|---|---|
| `users.id` = `auth.users.id` | From the JWT `sub` claim; `FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE`. |
| `users.primary_email` | Copied (lower-cased) from the JWT `email` claim when the row is created, and synced on `GET /me`. |
| `users.first_name`, `last_name` | Typed in onboarding (both required, ≤ 100 chars); changeable with `PATCH /me`. |
| `users.full_name` | The name as written on the résumé, if any; may differ from first + last. |
| `users.target_role`, `experience_level`, `graduation_year`, `preferred_location` | Asked in onboarding. `graduation_year` is 2000 … current year + 4. |
| `users.university` | Confirmed on the review page: pre-filled with the first school in the résumé's education (else the account's current one, else University of Wisconsin–Madison). Changeable with `PATCH /me`. |
| `users.terms_accepted_at` | The sign-up time, `auth.users.created_at`: sign-up can't be submitted without ticking the terms box, and Supabase writes this time, so the browser can't change it. The consent itself (`accept_terms: true`) is read from `user_metadata`. |
| `resumes` | One row per confirmed résumé (`confirmed_data` = the reviewed classification, `schema_version` `"1"`); `users.active_resume_id` is the newest. The child tables (`resume_experiences`, …) are not filled yet. |

Password reset is P1, so in P0 a user who forgets their password cannot recover the account on their own.

## 6. API and sessions

Sign-up, login and logout are not FastAPI endpoints: the frontend calls Supabase Auth directly. Every FastAPI endpoint below needs a valid Supabase JWT (`Authorization: Bearer <access_token>`).

| Method & path | Body | Success | Errors |
|---|---|---|---|
| `POST /me` | accept_terms, first_name, last_name, university, target_role, experience_level, graduation_year, preferred_location, resume (original_filename, parser, ocr_pages, agent_name, classification). The email comes from the token | `201` `{user}`; creates the `users` row and its first, active résumé | `401`, `403` email not confirmed, `409` already created, `422` |
| `GET /me` | — | `{user}`; `null` until onboarding is finished | `401` |
| `PATCH /me` | any of first_name, last_name, university, target_role, experience_level, graduation_year, preferred_location | `200` user | `401`, `403` onboarding not finished, `422` |
| `GET /me/resume` | — | `200` the active résumé `{id, original_filename, file_type, classification, created_at}` | `401`, `403`, `404` none |
| `POST /me/resumes` | as `resume` above | `201`; becomes the active résumé; empty contact fields on `users` are filled from it | `401`, `403`, `422` |

Backend validation mirrors `frontend/lib/validation/auth.ts`; the frontend checks are only for user experience.

**[DECIDED] Supabase Auth** (2026-10-11).

**Frontend**
- Uses `@supabase/supabase-js` with `@supabase/ssr`, so the Supabase session lives in cookies that Next.js can read (route guard, §7).
- Sign-up: `supabase.auth.signUp({ email, password, options: { data: { accept_terms: true }, emailRedirectTo: <site>/auth/confirm } })`. No session is returned until the email is confirmed; the page says "Check your email".
- `/auth/confirm` (new Next.js route) exchanges the link's token for a session, then calls `POST /me` with the terms consent from `user_metadata` and sends the user to `/onboarding`. The backend validates it like any other input. Login: `signInWithPassword`. Logout: `signOut`. **[DECIDED]** No "Remember me" checkbox: Supabase keeps users logged in until they log out, so the checkbox would do nothing.
- Calls to FastAPI go through `frontend/lib/api/client.ts` (PR #9), which adds `Authorization: Bearer <access_token>` from the current session. No cross-site cookies are sent to FastAPI, so `credentials: "include"` is not needed.
- New env vars: `NEXT_PUBLIC_SUPABASE_URL` and the project's publishable (anon) key. These are designed to be public; the service-role/secret key never goes to the frontend.

**Backend**
- A `get_current_user` dependency verifies the JWT on every request: signature (via the project's JWKS endpoint, `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, if the project uses asymmetric signing keys; otherwise the legacy JWT secret from `.env`), `exp` (60 s clock leeway), `aud == "authenticated"`, `iss == <SUPABASE_URL>/auth/v1`, and that the header's `alg` matches the signing key. A missing or invalid token is `401`; signing keys that can't be fetched are `503`. The shared project uses asymmetric signing keys (ES256, checked 2026-10-14, see `backend/README.md`). Library: `PyJWT`.
- It returns the user id (`sub`) and email. `GET /me`, `POST /me` and `POST /resumes/analyze` work before the `users` row exists; the other endpoints return `403` until onboarding is finished.
- `POST /me` also reads `auth.users.email_confirmed_at` and returns `403` until the email is confirmed, so an account can't claim an email it doesn't own even if **Confirm email** is turned off in the dashboard.
- If `GET /me` fails right after login, the browser is signed out again so no unusable session is left behind.
- Logout signs out this browser only (`signOut({ scope: "local" })`), not the user's other devices.
- Logged-out visits to a protected page go to `/login?next=<page>`; a `401` from the API signs this browser out and does the same. After login the user returns to `next` (same-site paths only, never an auth page); a newly created account goes to onboarding first.
- New env var: `SUPABASE_URL` (plus `SUPABASE_JWT_SECRET` only if the project uses the legacy secret).

**Rules**
- Passwords never reach our backend or database. They go from the browser straight to Supabase Auth.
- Tokens are never logged.
- **[DECIDED] P0 rate limiting** on sign-up and login uses Supabase Auth's built-in rate limits (configured in the Supabase dashboard), since those requests don't go through FastAPI.
- Auth settings (rate limits, email confirmation, redirect URLs) are changed in the Supabase dashboard, not by migrations. Whoever changes one records it in `backend/README.md`.
- The Supabase Data API is disabled (backend README); Supabase Auth is a separate service. We still have to confirm sign-up works with that setting.

**[DECIDED] Email confirmation is on in P0.** P0 is used for testing only, so Supabase's built-in email sender is enough. Limits to know:
- The built-in sender is meant for testing: it has a low hourly limit, and may only deliver to the project's team members' addresses. Testers sign up with their own (team) emails; to check the current limits, see Supabase's Auth → Emails docs.
- The confirmation link needs the right Site URL and redirect URL (`http://localhost:3000/auth/confirm` for local work) in Supabase Auth → URL Configuration.
- Real users (P1) need custom SMTP (P1-2).

## 7. Frontend changes

1. `signup-form.tsx`: email, password, confirm password (must match) and the terms checkbox; `supabase.auth.signUp` with the terms consent as `user_metadata`, then a "Check your email" state. New `/auth/confirm` route (§6). `login-form.tsx`: `signInWithPassword`. Add a logout action to the user menu.
2. Register the Supabase access token with `setAccessTokenGetter` in `lib/api/client.ts`, so every API call sends it.
3. Route guard (`proxy.ts`): no Supabase session → `/login`. After login or confirmation, a user without a `users` row goes to `/onboarding`, which creates it (`POST /me`). The onboarding check is P2-2.
4. API types come from FastAPI's `/openapi.json` (ADR-002), not written by hand.

**[DECIDED] Sign-up asks only for email and password** (typed twice, checked in the browser, plus the terms checkbox; changed 2026-10-20, it had no confirmation field before). First and last name, university, target role, graduation year and experience level are asked in onboarding, which already has these fields on `dev` (PR #11); saving them (frontend and API) is owned by onboarding. `backend/app/core/options.py` keeps the allowed values for that.

## 8. Security and privacy checklist

- [ ] Passwords only ever go to Supabase Auth; access tokens are never logged
- [ ] Only the publishable key in the frontend; secret keys only in backend `.env`
- [ ] Every endpoint except `/health` requires a valid token; data is always looked up by the token's user id, never an id from the request
- [ ] CORS stays limited to `CORS_ORIGINS` (already the case)
- [ ] Deleting a Supabase account removes its `users` row and résumés (cascade)

## 9. Testing

| Level | What |
|---|---|
| Unit | JWT verification (valid, expired, wrong `aud`, wrong issuer, bad signature, legacy HS256) with a locally generated key |
| API (FastAPI `TestClient`; auth and the database layer faked) | `POST /me` happy path; `401` without a token; `403` unconfirmed email; `409` on a second `POST /me`; `422` on bad fields or a missing name; `403` from `PATCH /me` and the résumé endpoints before onboarding is finished |
| Database (`tests/test_accounts_postgres.py`, throwaway Postgres, skipped without `TEST_DATABASE_URL`) | Real migrations; account + first résumé, newer résumé becomes active, cascade from `auth.users`, email uniqueness, the `auth.users` foreign key |
| Manual | full sign-up → confirm → login flow in the browser against the shared Supabase project before merging to `dev` |

Existing CI (`unittest`, no DB) must keep passing; tests that need a DB are skipped when the env vars aren't set.
