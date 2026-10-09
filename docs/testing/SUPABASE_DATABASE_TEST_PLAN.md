# CareerGPS Supabase Database Test Plan

[![Backend baseline checks](https://github.com/CS620-Microsoft-1/careergps/actions/workflows/backend-baseline-tests.yml/badge.svg?branch=test%2Fdatabase-rls)](https://github.com/CS620-Microsoft-1/careergps/actions/workflows/backend-baseline-tests.yml)

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
| DB-011 | Client changes a user ID in the request | Backend authorization rejects cross-user access | NOT RUN |
| DB-012 | Limited application database role connects | Required operations work without administrator privileges | BLOCKED — role not created |
| DB-013 | Secret scan and Git status | `.env` and credentials are absent from tracked files | PASS |

## Baseline automation

The workflow at `.github/workflows/backend-baseline-tests.yml` runs on:

- Pushes to `test/database-rls` that change backend, test-document, or workflow files.
- Pull requests targeting `dev` that change those files.

It performs seven checks without loading the real `.env` file or connecting to the shared database:

1. `.env` and `.venv` paths are ignored by Git.
2. Sensitive environment files and virtual environments are not tracked.
3. `.env.example` contains placeholders rather than real credentials.
4. Required backend dependencies are declared.
5. Alembic has exactly one migration head.
6. The `User` model has the expected table, columns, and email constraints.
7. A committed migration enables RLS on `users`.

These checks validate repository configuration only. They do not prove that the remote database is reachable or that future user-level RLS policies correctly isolate data.

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
2. A reliable relationship between `public.users.id` and the authenticated identity, such as Supabase Auth `auth.users.id`.
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
