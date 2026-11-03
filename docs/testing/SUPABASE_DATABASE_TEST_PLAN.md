# CareerGPS Supabase Database Test Plan

[![Backend baseline checks](https://github.com/CS620-Microsoft-1/careergps/actions/workflows/backend-baseline-tests.yml/badge.svg?branch=dev)](https://github.com/CS620-Microsoft-1/careergps/actions/workflows/backend-baseline-tests.yml)

This is the living test document for the shared CareerGPS PostgreSQL database hosted on Supabase. Update it whenever the schema, authentication model, database role, RLS policies, or migration state changes.

## Current verified state

Last verified: 2026-10-09

Branch: `dev`

Commit: `f133375`

Environment: Shared Supabase PostgreSQL

| Check | Expected result | Current result | Status |
| --- | --- | --- | --- |
| Python dependencies import | SQLAlchemy, psycopg, Alembic and dotenv load | Passed | PASS |
| Database connection | Connection succeeds | Connected to `postgres` | PASS |
| PostgreSQL server | Server responds | PostgreSQL 17.11 | PASS |
| Alembic revision | `8cb9c0fe6e22 (head)` | `8cb9c0fe6e22 (head)` | PASS |
| `public.users` table | Table exists | Exists | PASS |
| Initial user count | Empty table | 0 rows | PASS |
| RLS enabled | Enabled on `public.users` | Enabled | PASS |
| `.env` excluded from Git | Ignored | Ignored by `backend/.gitignore` | PASS |

## Important security limitation

The successful connection currently uses the shared `postgres` role. This is a privileged database role and normally bypasses Row Level Security. The passing connection and table checks therefore do **not** prove that one application user is prevented from reading or changing another user's data.

RLS is enabled on `public.users`, but the initial migration does not create user-access policies. User-level authorization remains incomplete until authentication is connected to the database and explicit policies are added and tested.

## Test matrix

| ID | Scenario | Expected result | Status |
| --- | --- | --- | --- |
| DB-001 | Backend connects with the configured `DATABASE_URL` | Connection succeeds without exposing credentials | PASS |
| DB-002 | Alembic checks the shared database | Database reports the repository's current head revision | PASS |
| DB-003 | Query `public.users` | Table exists and can be queried by the backend role | PASS |
| DB-004 | Inspect `public.users` RLS flag | RLS is enabled | PASS |
| DB-005 | Anonymous client reads `public.users` | Request is denied or returns no rows, according to policy | NOT RUN |
| DB-006 | Authenticated user reads their own profile | Only that user's row is returned | NOT RUN |
| DB-007 | Authenticated user reads another profile | Access is denied and no other user's data is returned | NOT RUN |
| DB-008 | Authenticated user updates their own profile | Allowed fields are updated | NOT RUN |
| DB-009 | Authenticated user updates another profile | Update is denied | NOT RUN |
| DB-010 | Authenticated user deletes another profile | Delete is denied | NOT RUN |
| DB-011 | Client changes a user ID in the request | Backend authorization rejects cross-user access | PARTIAL — `/me` endpoints only use the user id from the verified token, never one from the request (`tests/test_me.py`); not yet run against the shared DB |
| DB-012 | Limited application database role connects | Required operations work without administrator privileges | BLOCKED — role not created |
| DB-013 | Secret scan and Git status | `.env` and credentials are absent from tracked files | PASS |
| DB-014 | Alembic after applying `02a858fed0df` (users + résumé tables) | `alembic current` shows `02a858fed0df (head)`; `alembic check` reports no new operations | NOT RUN — not applied yet |
| DB-015 | Inspect RLS on `resumes`, `resume_experiences`, `resume_educations`, `resume_projects`, `resume_achievements`, `resume_skills` | RLS is enabled on all six | NOT RUN |
| DB-016 | Insert a `users` row whose `id` is not in `auth.users` | Rejected by `users_id_fkey` | NOT RUN |
| DB-017 | Delete a test user that has résumés | Their résumés and all child rows are deleted (cascade) | NOT RUN |
| DB-018 | Delete a user's active résumé | `users.active_resume_id` becomes NULL; the user row remains | NOT RUN |
| DB-019 | Set `users.active_resume_id` to another user's résumé | Rejected by `fk_users_active_resume` | NOT RUN |
| DB-020 | Insert a child row whose `user_id` differs from its résumé's owner | Rejected by the `(resume_id, user_id)` foreign key | NOT RUN |
| DB-021 | Insert the same skill twice from the same source (e.g. listed) | Second insert rejected by `uq_resume_skills_evidence` (NULLs count as equal) | NOT RUN — runnable now that résumés have skill rows |
| DB-022 | Insert a skill whose source link doesn't match `source` (e.g. `project` without `source_project_id`) | Rejected by `ck_resume_skills_source_link` | NOT RUN — runnable now that résumés have skill rows |
| DB-023 | Run `python -m scripts.backfill_resume_children`, then compare each résumé's child rows with its `confirmed_data` | Every résumé reports `ok`; `listed` skills = Technical Skills without duplicates; one project/experience/education/achievement row per non-blank entry | NOT RUN — dry run passed for 6/6 résumés (2026-10-29) |

## Baseline automation

The workflow at `.github/workflows/backend-baseline-tests.yml` runs on:

- Pushes to `test/database-rls` that change backend, test-document, or workflow files.
- Every pull request targeting `dev`, including frontend-only pull requests, so the required `baseline` status check is always created.

The configuration tests in `tests/test_baseline_configuration.py` check, without loading the real `.env` file or connecting to the shared database:

1. `.env` and `.venv` paths are ignored by Git.
2. Sensitive environment files and virtual environments are not tracked.
3. `.env.example` contains placeholders rather than real credentials.
4. Required backend dependencies are declared.
5. Alembic has exactly one migration head.
6. The `User` model has the expected table, columns, and `primary_email` constraints, and no Python-generated id.
7. The six résumé tables are registered and carry their owner columns.
8. Committed migrations enable RLS on `users`, `job_postings`, `ingest_runs`, and the six résumé tables.
9. A committed migration links `users.id` to Supabase Auth (`auth.users`).

These checks validate repository configuration only. They do not prove that the remote database is reachable or that future user-level RLS policies correctly isolate data.

The same workflow also runs the auth tests from `feat/supabase-auth`. None of them connect to the shared database; API tests use in-memory SQLite:

- `test_security.py`: Supabase token verification (expired, wrong audience/issuer, wrong key, unsigned tokens are rejected).
- `test_me.py`: onboarding (`POST /me`), `GET /me`, `PATCH /me` and the résumé endpoints, with the database layer faked, including missing or invalid tokens. `test_accounts_postgres.py` runs the same service against a throwaway Postgres when `TEST_DATABASE_URL` is set (skipped in CI).

## Local verification steps

Run commands from `backend/` with the virtual environment activated.

```powershell
.\.venv\Scripts\Activate.ps1
python -X utf8 -m app.db.check_connection
python -X utf8 -m alembic current
```

Expected output includes:

```text
Connected ✅
8cb9c0fe6e22 (head)
```

Never paste `DATABASE_URL` into this document, Git commits, pull requests, issues, test output, screenshots, or team-wide chat. Store it only in the ignored `backend/.env` file and share it through an approved private channel.

## RLS test prerequisites

Before DB-005 through DB-011 can be completed, the project needs:

1. A confirmed authentication provider and user identity model.
2. A reliable relationship between `public.users.id` and the authenticated identity, such as Supabase Auth `auth.users.id`. Migration `02a858fed0df` adds this foreign key.
3. Explicit RLS policies for each required operation: `SELECT`, `INSERT`, `UPDATE`, and `DELETE`.
4. At least two isolated test users with synthetic data.
5. A non-administrator client or application role that does not bypass RLS.
6. Backend authorization tests in addition to database-policy tests.

## Update procedure

When a database-related PR changes the schema or security model:

1. Record the branch and commit tested.
2. Run the connection and Alembic checks.
3. Run every affected test case in the matrix.
4. Change statuses only when supported by observed results.
5. Add a dated entry to the test log.
6. Never record credentials or real personal data.

## Test log

### 2026-10-09 — Initial shared database verification

- Verified the local `dev` branch at commit `f133375`.
- Created an isolated Python virtual environment and installed backend dependencies.
- Connected successfully to the shared Supabase PostgreSQL database.
- Confirmed PostgreSQL 17.11 and Alembic revision `8cb9c0fe6e22 (head)`.
- Confirmed `public.users` exists, contains 0 rows, and has RLS enabled.
- Confirmed `.env` is ignored by Git.
- Did not run user-isolation tests because authentication, RLS policies, and a limited application role are not yet implemented.

### 2026-10-09 — Application-data state recheck

- Queried the shared database using read-only SQL.
- Confirmed the `public` schema contains `alembic_version` and `users`.
- Confirmed `public.users` still contains 0 rows.
- No database contents were modified.

### 2026-10-09 — Baseline automation added

- Created branch `test/database-rls` from the latest `dev`.
- Added seven credential-free baseline configuration tests.
- Added a GitHub Actions workflow for pushes to the test branch and relevant PRs targeting `dev`.
- Ran all seven tests locally; all passed.
- Confirmed the first GitHub Actions run completed successfully.
- Confirmed the tests do not connect to the shared database or expose `DATABASE_URL`.

### 2026-10-09 — Required-check trigger coverage updated

- Updated the workflow so every pull request targeting `dev` creates the required `baseline` status check, including frontend-only pull requests.
- Kept the existing path filter for direct pushes to `test/database-rls`.
- Updated the workflow badge to report the protected `dev` branch.
- Ran all seven baseline configuration tests locally; all passed.
- Did not connect to or modify the shared Supabase database.

### 2026-10-20 — Users and résumé tables migration prepared

- Branch `feat/resume-storage-schema` from `dev` (`b4cf5e8`).
- Added migration `02a858fed0df`: extends `users` (rename `email` → `primary_email`, onboarding and résumé contact columns, `active_resume_id`, foreign key to `auth.users`) and creates six résumé tables with RLS enabled.
- Confirmed `public.users` contains 0 rows before writing NOT NULL columns without defaults.
- Reviewed the upgrade and downgrade SQL with `alembic upgrade --sql` / `alembic downgrade --sql`. The migration was not applied; the shared database stays at `6ef2e4581bd9` until the PR is merged.
- Added DB-014 to DB-022 (NOT RUN) and updated the baseline tests; all 46 backend tests pass locally.

### 2026-10-26 — Authenticated Skill Gaps connection check

- Integrated `origin/dev` at `cc6e458` into the local `test/skill-gaps` branch; no push or merge into `dev`.
- Connected to the configured shared PostgreSQL database using `SET TRANSACTION READ ONLY` and `SELECT 1`.
- Confirmed the required schema columns exist: `users.id`, `users.active_resume_id`, `resumes.id`, `resumes.user_id`, and `resumes.confirmed_data` (JSONB).
- The running main API returned HTTP 200 for `/health` and `/health/db`; authenticated Skill Gaps endpoints rejected missing login with HTTP 401.
- No user records or resume contents were read, no migrations were applied, and no shared data was modified.
- User ownership, saved-resume selection and result isolation were tested with synthetic accounts and a mocked Agent. These are application tests, not a live PostgreSQL RLS-policy verification; the RLS matrix remains unchanged.


### 2026-10-26 — Real user Skill Gaps ownership and snapshot audit

- The user completed a real AI Engineer analysis after email confirmation and Review save. The API returned 201 for account/resume creation and 202 for one Skill Gaps submission, followed by successful status/latest reads.
- A read-only audit restricted to that run's user and resume verified email confirmation, the active resume pointer, resume ownership, identical database/input snapshots, content hash and report identifiers. No personal information or credentials are recorded here.
- Skill Gaps made one model call in 50.426 seconds; no automatic repair or summary call occurred. The audit did not invoke the Agent or modify shared data.
- The report scored 20/23 skills; three invalid references remained null/pending, with no arithmetic or saved-response replay discrepancies. Results remain local JSON rather than database records.
- This checks application ownership for the tested account. Cross-account and RLS-policy checks against the real shared database were not performed; their matrix statuses remain unchanged.

### 2026-10-29 — Résumé child rows (dry run)

- Branch `feat/resume-child-rows` from `dev` (`9e5f82c`). Confirmed résumés now fill the five child tables from `confirmed_data`; `scripts/backfill_resume_children.py` rebuilds stored résumés.
- `alembic current` on the shared database: `9c4d2a7f1b3e`. Before the change: 6 résumés, 0 child rows.
- `--dry-run` sent every row to the shared database and rolled back: 6/6 résumés passed all constraints (264 skills, 11 projects, 23 experiences, 7 educations, 3 achievements). The tables still had 0 rows afterwards.
- `tests/test_accounts_postgres.py` passed 12/12 against a throwaway Postgres 17 container with every migration applied.
- Only ids and counts were printed; no résumé content was read into logs. Added DB-023.
