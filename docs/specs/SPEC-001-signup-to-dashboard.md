# SPEC-001: Sign up → Résumé parsing → Dashboard

- **Status:** Draft
- **Date:** 2026-10-10
- **Scope:** Account creation, profile, résumé upload, async résumé parsing, user confirmation
- **Related:** [ADR-001](../decisions/ADR-001-CareerGPS-Frontend.md), [ADR-002](../decisions/ADR-002-CareerGPS-Backend.md), [Supabase test plan](../testing/SUPABASE_DATABASE_TEST_PLAN.md)

Items marked **[OPEN]** need a team decision before or during implementation. Each one has a proposed default.
Items marked **[DECIDED]** were settled on 2026-10-10. Priorities (P0 / P1 / P2) are listed in §3.

---

## 1. Goal

A new student can create an account, tell us their career goal, upload a résumé, check what we extracted from it, and land on the dashboard with a confirmed, structured profile.

Nothing extracted by the LLM counts as profile data until the user has confirmed it.

## 2. Current state (as of `dev` @ `055c0bb`)

| Area | What exists |
|---|---|
| Frontend | `/signup`, `/onboarding`, `/login`, `/dashboard` screens. Forms validate with zod (`frontend/lib/validation/auth.ts`) and then just `router.push` to the next page. No API calls. |
| Signup form | full name, email, password (8–128), confirm password, target role, graduation year, university, experience level, accept terms |
| Onboarding form | target role, graduation year, location, experience level, résumé (PDF or DOCX, ≤ 10 MB) |
| Backend | FastAPI app with `/health` and `/health/db` only. `get_db` session dependency. |
| Database | `users` (id, email, full_name, created_at, updated_at), RLS enabled, no policies. The backend connects as `postgres` and bypasses RLS. |
| CI | Baseline checks run on every PR to `dev` (`backend/tests/test_baseline_configuration.py`). They assert that `users.email` is unique and **not nullable**. |
| Team work in progress | A teammate: `pdfplumber` text extraction tested on text-based PDFs (`resume_parser_test`). Shangyuan and that teammate: testing OCR models for scanned PDFs. |

## 3. Priorities

- **P0**: the first release. Sections 4–12 describe P0 in detail.
- **P1**: the next release, right after P0.
- **P2**: later.

The **Basis** column says whether the priority was decided by the team (**Decided**) or is only a proposal still to be confirmed (**Proposed**, with the open item in brackets).

### P0

| # | Task | Basis |
|---|---|---|
| P0-1 | Sign up with **email** + password, using **Supabase Auth**, with **email confirmation on** (§8.1) | Decided |
| P0-2 | Log in, log out, session via Supabase Auth; FastAPI verifies the Supabase JWT (§8.1) | Decided |
| P0-3 | Create `users` + `profiles` rows on the first login after email confirmation (`POST /me`, goal fields saved at sign-up); onboarding adds location (`PATCH /me/profile`) | Decided |
| P0-4 | Route guard: not logged in → `/login`; onboarding not finished → `/onboarding` | Decided |
| P0-5 | Upload a résumé, **PDF only**, ≤ 10 MB, checked by content (§7.1) | Decided |
| P0-6 | **One résumé per user** (unique `resumes.user_id`) | Decided |
| P0-7 | Store the file in a private **Supabase Storage** bucket (§7.1) | Decided |
| P0-8 | Text extraction with `pdfplumber` (text, pages, links); scanned PDFs fail with `no_text` for now | Decided (OCR in P1: P1-5) |
| P0-9 | LLM extraction with **Azure OpenAI** into `ResumeExtraction`, schema-validated, one retry (§7.3) | Decided |
| P0-10 | Run parsing with FastAPI `BackgroundTasks`; frontend polls (§7.4) | Decided |
| P0-11 | Status machine, retry from `failed`, stuck rows marked `failed` when read (§6) | Proposed |
| P0-12 | Review page: show, edit, confirm; confirm writes the structured tables (§5.4, §9) | Decided |
| P0-13 | A `failed` résumé can be replaced; a confirmed one **cannot** | Decided |
| P0-14 | Frontend: DOCX removed from upload | Decided |
| P0-15 | Goal fields (target role, graduation year, experience level) **only on sign-up**; remove them from onboarding | Decided |
| P0-16 | Rate limit sign-up and login (Supabase Auth's built-in limits, configured in the dashboard) | Decided |
| P0-17 | Security checklist (§10) and tests (§11) | Decided |

### P1

| # | Task | Basis |
|---|---|---|
| P1-0 | Replace the résumé after confirming; confirm overwrites the structured rows | Decided |
| P1-1 | Password reset by email (Supabase Auth built-in; needs custom SMTP) | Decided |
| P1-2 | Custom SMTP so confirmation and reset emails reach real users | Proposed |
| P1-3 | Skip re-parsing an identical upload (`resumes.sha256`) | Proposed |
| P1-4 | Parser quality set: sample résumés with expected output (§11) | Proposed |
| P1-5 | OCR for scanned PDFs: when text extraction finds too little text, run OCR instead of failing with `no_text`; failed `no_text` résumés can then be retried (the original PDF is kept). Model chosen from the team's OCR test | Decided |

### P2

| # | Task | Basis |
|---|---|---|
| P2-1 | Multiple résumés per user | Decided |
| P2-2 | DOCX upload (`python-docx`) | Proposed |
| P2-4 | Real job queue (e.g. arq + Redis) instead of `BackgroundTasks` | Proposed |
| P2-5 | Push (SSE) instead of polling | Proposed |
| P2-6 | SSO login via Supabase Auth OAuth providers (buttons exist as UI only) | Proposed |

## 4. End-to-end flow

```text
/signup ──supabase.auth.signUp()──▶ Supabase Auth creates the account and emails a confirmation link
   │                                  (profile fields saved in user_metadata)
   │
confirmation link ──▶ /auth/confirm ──▶ session created
   │    ──POST /me (Bearer JWT)──▶ users + profiles rows created from user_metadata
   │
/onboarding ──PATCH /me/profile──▶ profile updated
   │        ──POST /resumes (multipart)──▶ file stored, resumes row = pending
   │                                         │
   │                                   background job
   │                                         ▼
   │                          parsing → text → LLM → parsed_data, status = parsed
   │                                         (or failed + error_code)
   ▼
/onboarding/review ──GET /me (résumé id), then GET /resumes/{id} every 2 s until parsed/failed
   │   "Here is what we identified" — user edits fields
   │
   └──POST /resumes/{id}/confirm──▶ one transaction: write structured tables,
                                     status = confirmed
   ▼
/dashboard
```

## 5. Data model

All tables get RLS enabled with no policies, as with `users` (the backend is the only client).
All new migrations are additive.

Migrations follow the shared database rules in `backend/README.md`: generated with Alembic and reviewed in the PR, never created in the Supabase dashboard, applied from `dev` after the PR is merged, by one person who announces it in the team chat, and `ENABLE ROW LEVEL SECURITY` in every new table's migration.

### 5.1 `users` (change)

**[DECIDED] Users sign up and log in with email + password through Supabase Auth.** Supabase keeps accounts and password hashes in its own `auth.users` table; our database never stores passwords.

| Change | Notes |
|---|---|
| `users.id` = `auth.users.id` | No default UUID for new rows; the id comes from the JWT `sub` claim. Add `FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE` **by hand** in the migration (autogenerate doesn't know the `auth` schema). |
| `users.email` | Kept (unique, not null), copied from the JWT `email` claim when the row is created, so the baseline CI test stays as it is. `auth.users.email` is the source of truth; P1 email changes must update both. |
| `users.full_name` | From the sign-up form (via `user_metadata` and `POST /me`). |

Password reset is P1, so in P0 a user who forgets their password cannot recover the account on their own.

### 5.2 `profiles` (new, 1:1 with `users`)

| Column | Type | Notes |
|---|---|---|
| `user_id` | `uuid PK, FK users.id ON DELETE CASCADE` | |
| `target_role` | `text NOT NULL` | One of `TARGET_ROLES` in `frontend/lib/options.ts`. Checked by the backend, not a DB enum, so the list can change without a migration. |
| `experience_level` | `text NOT NULL` | `Internship` or `Full-time` |
| `graduation_year` | `smallint NOT NULL` | current year … current year + 4 |
| `university` | `text NOT NULL` | ≤ 150 chars |
| `location` | `text NULL` | ≤ 100 chars; filled in onboarding |
| `phone`, `links` | `text NULL`, `jsonb NULL` | from the confirmed résumé's contact section |
| `terms_accepted_at` | `timestamptz NOT NULL` | when the user accepted the terms at sign-up (résumés go to Azure OpenAI, so we keep a record of consent) |
| `onboarding_completed_at` | `timestamptz NULL` | set when a résumé is confirmed |
| `created_at`, `updated_at` | `timestamptz` | same pattern as `users` |

### 5.3 `resumes` (new)

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid PK` | |
| `user_id` | `uuid FK users.id ON DELETE CASCADE`, indexed | |
| `storage_key` | `text NOT NULL` | `{user_id}/{resume_id}.pdf` inside the `resumes` bucket. Never built from the uploaded file name. |
| `original_filename` | `text NOT NULL` | shown in the UI only, ≤ 255 chars |
| `content_type` | `text NOT NULL` | |
| `size_bytes` | `integer NOT NULL` | |
| `sha256` | `text NOT NULL` | stored in P0; used in P1 to skip re-parsing an identical upload (P1-4) |
| `status` | `text NOT NULL` | see §6 |
| `error_code` | `text NULL` | machine-readable, see §6 |
| `extracted` | `jsonb NULL` | text extraction output (§7.2) |
| `parsed_data` | `jsonb NULL` | LLM output after schema validation (§7.3) |
| `parser_version` | `text NULL` | e.g. `v1:<model-id>`; lets us re-run old résumés later |
| `created_at`, `updated_at`, `parsed_at`, `confirmed_at` | `timestamptz` | |

### 5.4 Structured tables (written only on confirm)

| Table | Columns (besides `id`, `user_id`, `resume_id`, timestamps) |
|---|---|
| `educations` | `school`, `degree`, `field_of_study`, `start_date`, `end_date`, `gpa` |
| `experiences` | `company`, `title`, `location`, `start_date`, `end_date`, `is_current`, `description` (the bullet points, one per line) |
| `skills` | `name`, `category` (`language` / `framework` / `tool` / `other`); unique on (`user_id`, lower(`name`)) |
| `projects` | `name`, `description`, `url`, `technologies jsonb` (list of strings) |

Contact info (name, email, phone, links) from the résumé is shown for confirmation but not copied over `users.full_name`. Phone and links go into `profiles` as nullable columns (`phone`, `links jsonb`).

**[DECIDED] P0: one résumé per user.** Enforced with a unique constraint on `resumes.user_id`. Multiple résumés per user are **P2**.

**[DECIDED] P0: a confirmed résumé cannot be replaced.** `POST /resumes` returns `409` if the user already has a résumé that is not `failed`. **P1:** replacing is allowed; confirming the new one overwrites the structured rows in one transaction.

**[DECIDED] P0: a résumé that failed to parse can be replaced.** Uploading a new file deletes the `failed` row and its stored file. Only a `confirmed` résumé is locked in P0.

## 6. Résumé status

```text
pending ──▶ parsing ──▶ parsed ──▶ confirmed
               │
               └──▶ failed   (user can retry → pending)
```

| `error_code` | Meaning | User-facing message |
|---|---|---|
| `no_text` | Extracted text is under 200 characters (most likely a scanned PDF) | "We couldn't read text from this file. Try exporting it again as a PDF." |
| `llm_invalid_output` | Output failed schema validation after one retry | "Something went wrong reading your résumé. Try again." |
| `llm_unavailable` | Provider timeout/error | same as above |
| `internal` | anything else | same as above |

Rules:
- Only the transition `parsed → confirmed` writes the structured tables.
- A row still `pending` or `parsing` more than 10 minutes after its last update (e.g. the server restarted mid-job) is marked `failed` / `internal` the next time it is read (`GET /resumes/{id}`, `GET /me`), so the user can retry. Nothing runs at server startup.

## 7. Parsing pipeline

### 7.1 Upload checks (backend, before storing)

1. Size ≤ 10 MB. Reject larger requests early with 413.
2. Type check by **content**, not the browser's MIME type: a PDF must start with `%PDF-`.
3. PDF opens without errors and has ≤ 10 pages.
4. Stored as `storage_key`; the response never includes the storage URL.

**[DECIDED] PDF only.** The frontend currently also accepts DOCX, so `RESUME_ACCEPT` / `RESUME_MIME_TYPES` in `frontend/lib/options.ts`, the zod message and the dropzone text change to PDF only.

**[DECIDED] Object storage: Supabase Storage.**
- One **private** bucket, `resumes`. No public URLs; the frontend never reads files directly.
- Only the backend reads and writes it, using the Supabase service-role/secret key from backend `.env`.
- The bucket is created in the Supabase dashboard (it is project configuration, not schema) and recorded in `backend/README.md`, like the auth settings (§8.1).
- Bucket file size limit set to 10 MB and allowed type to `application/pdf`, as a second check behind the backend's own checks.
- Deleting a user must also delete their files: database cascades don't reach Storage, so the backend deletes the object explicitly.

### 7.2 Text extraction

The plan named `unpdf` / `pdfjs-dist`, but those are JavaScript libraries and parsing runs in the Python backend (ADR-002). Use:

- **`pdfplumber`** (MIT). The team already tested it on text-based PDFs (`resume_parser_test`). Avoid PyMuPDF: it is AGPL.
- Keep the text whole; don't split it into sections with rules. Résumés use too many different headings; the LLM step does the structuring.
- Extract, as the test did: full text, text per page, and **hyperlink targets** (LinkedIn, GitHub and portfolio links are often only in the link, not in the visible text). All of it goes to the LLM.
- Store this in a new `resumes.extracted` column (`jsonb`: `full_text`, `pages[]`, `links[]`) so a parse can be re-run or debugged without re-reading the file. It is personal data: same handling as `parsed_data`, never logged.
- If extracted text is under 200 characters, treat it as scanned: `failed` / `no_text`.

**[DECIDED] OCR for scanned PDFs is P1** (P1-5). P0 shows the `no_text` message. The `no_text` check is where OCR plugs in, so the rest of the pipeline doesn't change when OCR is added. Which OCR model to use comes from the team's OCR test.

### 7.3 LLM extraction

- The LLM receives the extracted text and must answer in a fixed JSON schema (structured output / JSON schema mode). The same schema is defined once as a Pydantic model, `ResumeExtraction`, in `backend/app/schemas/resume.py`.
- Output is validated with that Pydantic model. On failure: one retry with the validation errors included in the prompt; then `failed` / `llm_invalid_output`.
- Every field is optional or may be an empty list. The prompt says: copy only what is in the text, never invent.
- The résumé text is wrapped as data, and the prompt says to ignore instructions inside it (prompt-injection defense).

```text
ResumeExtraction
├── contact: { full_name, email, phone, location, links[] }
├── education[]: { school, degree, field_of_study, start_date, end_date, gpa }
├── experience[]: { company, title, location, start_date, end_date, is_current, bullets[] }
├── projects[]: { name, description, url, technologies[] }
└── skills[]: { name, category }
```

Dates are strings in `YYYY-MM` or `YYYY` form, or `null`.

**[DECIDED] LLM provider: Azure OpenAI**, behind a small `LLMClient` interface so the provider can change. See [ADR-003](../decisions/ADR-003-CareerGPS-LLM-Provider.md). The exact model/deployment is chosen there. Note: résumé text is personal data sent to a third party; this must be in the privacy policy that the signup form asks users to accept.

### 7.4 Running it asynchronously

**[DECIDED] Background jobs in P0: FastAPI `BackgroundTasks`.** The upload request returns `202` right away; the task does the work. Because state lives in the `status` column, we can later swap in a real queue (e.g. arq + Redis) without changing the API.

The frontend polls (§8). No WebSockets or SSE in P0 (SSE is P2-5).

## 8. API

Sign-up, login and logout are not FastAPI endpoints: the frontend calls Supabase Auth directly (§8.1). Every FastAPI endpoint below needs a valid Supabase JWT (`Authorization: Bearer <access_token>`). Every `/resumes/{id}` endpoint checks `resume.user_id == current_user.id` and returns **404** (not 403) otherwise.

| Method & path | Body | Success | Errors |
|---|---|---|---|
| `POST /me` | full_name, target_role, graduation_year, university, experience_level, accept_terms | `201` `{user, profile}`; creates the `users` and `profiles` rows | `401`, `409` already created, `422` |
| `GET /me` | — | `{user, profile, latest_resume}`; all `null` until `POST /me` succeeds; `latest_resume` is the user's résumé summary (`id`, `status`, `error_code`, `original_filename`) | `401` |
| `PATCH /me/profile` | location (P0); goal fields once a settings page exists | `200` profile | `422` |
| `POST /resumes` | multipart `file` | `202` `{id, status: "pending"}` | `409` already has a résumé that is not `failed` (P0), `413`, `415`, `422` |
| `GET /resumes/{id}` | — | `{id, status, error_code, parsed_data}` | `404` |
| `POST /resumes/{id}/retry` | — | `202` (only from `failed`) | `404`, `409` |
| `POST /resumes/{id}/confirm` | edited `ResumeExtraction` | `200`, status `confirmed` | `404`, `409` if not `parsed`, `422` |

Backend validation mirrors `frontend/lib/validation/auth.ts`; the frontend checks are only for user experience.

### 8.1 Auth and sessions

**[DECIDED] Supabase Auth** (2026-10-11).

**Frontend**
- Uses `@supabase/supabase-js` with `@supabase/ssr`, so the Supabase session lives in cookies that Next.js can read (route guard, §9).
- Sign-up: `supabase.auth.signUp({ email, password, options: { data: <profile fields>, emailRedirectTo: <site>/auth/confirm } })`. No session is returned until the email is confirmed; the page says "Check your email".
- `/auth/confirm` (new Next.js route) exchanges the link's token for a session, then calls `POST /me` with the fields from `user_metadata` and sends the user to `/onboarding`. The backend validates them like any other input. Login: `signInWithPassword`. Logout: `signOut`. "Remember me" has no direct Supabase equivalent; P0 drops the checkbox or keeps it as UI only (to agree in PR 1).
- Calls to FastAPI go through `frontend/lib/api/client.ts` (PR #9), which adds `Authorization: Bearer <access_token>` from the current session. No cross-site cookies are sent to FastAPI, so `credentials: "include"` is not needed.
- New env vars: `NEXT_PUBLIC_SUPABASE_URL` and the project's publishable (anon) key. These are designed to be public; the service-role/secret key never goes to the frontend.

**Backend**
- A `get_current_user` dependency verifies the JWT on every request: signature (via the project's JWKS endpoint, `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, if the project uses asymmetric signing keys; otherwise the legacy JWT secret from `.env`), `exp`, and `aud == "authenticated"`. Which of the two the project uses is checked in PR 1. Library: `PyJWT`.
- It returns the user id (`sub`) and email. Endpoints other than `POST /me` return `403` if the `users` row doesn't exist yet.
- New env var: `SUPABASE_URL` (plus `SUPABASE_JWT_SECRET` only if the project uses the legacy secret).

**Rules**
- Passwords never reach our backend or database. They go from the browser straight to Supabase Auth.
- Tokens are never logged.
- **[DECIDED] P0 rate limiting** on sign-up and login uses Supabase Auth's built-in rate limits (configured in the Supabase dashboard), since those requests don't go through FastAPI.
- Auth settings (rate limits, email confirmation, redirect URLs) are changed in the Supabase dashboard, not by migrations. Whoever changes one records it in `backend/README.md`.
- The Supabase Data API is disabled (backend README); Supabase Auth is a separate service. PR 1 must confirm sign-up works with that setting.

**[DECIDED] Email confirmation is on in P0.** P0 is used for testing only, so Supabase's built-in email sender is enough. Limits to know:
- The built-in sender is meant for testing: it has a low hourly limit, and may only deliver to the project's team members' addresses. Testers sign up with their own (team) emails; to check the current limits, see Supabase's Auth → Emails docs.
- The confirmation link needs the right Site URL and redirect URL (`http://localhost:3000/auth/confirm` for local work) in Supabase Auth → URL Configuration.
- Real users (P1) need custom SMTP (P1-2).

## 9. Frontend changes

1. `signup-form.tsx`: `supabase.auth.signUp` with the profile fields as `user_metadata`, then a "Check your email" state. New `/auth/confirm` route (§8.1). `login-form.tsx`: `signInWithPassword`. Add a logout action to the user menu.
2. `onboarding-form.tsx` (upload needs a longer timeout than the 5 s default in `lib/api/client.ts`; a 10 MB file can take longer on a slow connection): drop target role, graduation year and experience level (they are on sign-up only); keep location and résumé. `PATCH /me/profile`, then `POST /resumes`, then go to the new `/onboarding/review` page. A `409` from the upload (a résumé already exists) also goes there.
3. New `/onboarding/review` page:
   - Finds the résumé through `GET /me` (`latest_resume`; P0 has one per user), so the URL needs no id and survives a refresh. No résumé → back to `/onboarding`; already confirmed → `/dashboard`.
   - Polls `GET /resumes/{id}` every 2 s, up to 2 minutes; shows a progress state, then "Check again".
   - `parsed`: an editable form built from `parsed_data` ("Here is what we identified"). Users can add, edit and delete items in each section.
   - `failed`: the message from §6, with "Try again" (retry) and "Upload a different file". For `no_text` only "Upload a different file" is shown: the same file would fail again.
   - "Looks right" → `POST /resumes/{id}/confirm` → `/dashboard`.
4. Route guard: no Supabase session → `/login`; session but `profile` is `null` → back to the sign-up profile fields; onboarding not complete → `/onboarding`.
5. API types come from FastAPI's `/openapi.json` (ADR-002), not written by hand.

**[DECIDED] Goal fields only on sign-up.** Target role, graduation year and experience level stay on sign-up and are removed from onboarding. Onboarding keeps location and the résumé.

## 10. Security and privacy checklist

- [ ] Passwords only ever go to Supabase Auth; access tokens are never logged
- [ ] Supabase service-role/secret key only in backend `.env`; only the publishable key in the frontend
- [ ] Résumé text and `parsed_data` are not written to logs either
- [ ] Upload type checked by file content; storage key never derived from user input
- [ ] Ownership checked on every résumé endpoint (404 for other users' IDs)
- [ ] `resumes` bucket is private; service-role key only in backend `.env`
- [ ] LLM prompt treats résumé text as untrusted data
- [ ] CORS stays limited to `CORS_ORIGINS` (already the case)
- [ ] Deleting a user removes their profile, résumés, structured rows (cascade) **and** stored files

## 11. Testing

| Level | What |
|---|---|
| Unit | JWT verification (valid, expired, wrong `aud`, bad signature) with a locally generated key; upload validation (wrong magic bytes, too big, too many pages); `ResumeExtraction` validation; status transitions (illegal ones rejected) |
| API (FastAPI `TestClient`; auth, LLM and storage faked) | `POST /me` → upload → poll → confirm happy path; `401` without a token; `409` on a second `POST /me`; 404 on another user's résumé; confirm while `pending` → 409; `no_text` path |
| Parser quality | 5–10 sample résumés (fake people) in `backend/tests/fixtures/` with expected output; reported as field-level match rate, not pass/fail, so it can run without CI calling the LLM |
| Manual | full flow in the browser against the shared Supabase DB before merging to `dev` |

Existing CI (`unittest`, no DB) must keep passing; tests that need a DB or the LLM are skipped when the env vars aren't set.

## 12. Suggested PR breakdown (P0)

Team workflow: one Jira ticket per PR, set to *In progress* before starting so two people don't build the same thing. Each PR is a feature branch into `dev`, includes its own tests, and must pass the required CI checks.

1. **Auth:** migration (`users.id` → `auth.users` FK, `profiles`); `get_current_user` JWT check; `POST /me`, `GET /me`, `PATCH /me/profile`; Supabase client in the frontend, sign-up/login/logout, `/auth/confirm`, bearer token in `lib/api/client.ts`; route guard; Supabase Auth settings (email confirmation, redirect URLs, rate limits).
2. **Upload:** `resumes` table, `resumes` Storage bucket and storage client, `POST /resumes`, `GET /resumes/{id}`; onboarding form uploads.
3. **Parsing:** text extraction, `LLMClient`, `ResumeExtraction`, background task, retry, stuck rows marked failed on read.
4. **Review & confirm:** structured tables migration, `POST /resumes/{id}/confirm`, `/onboarding/review` page.

PRs 1 and 2 touch different files and can be built in parallel; 3 depends on 2; 4 depends on 3 for real data but can start against a fake `parsed_data`.

## 13. Open problems

| # | Problem | Notes |
|---|---|---|
| P0-11 | Résumé status machine, incl. stuck jobs marked `failed` when read | Implemented as in §6; waiting for confirmation |
