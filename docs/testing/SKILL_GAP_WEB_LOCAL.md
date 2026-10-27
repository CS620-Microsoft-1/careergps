# Skill Gaps: authenticated local development

Skill Gaps runs in the normal CareerGPS application. Sign in, confirm the reviewed
resume, and open Dashboard. The backend loads the authenticated user's active
`resumes.confirmed_data`; browser storage is not a second resume source.

One Agent call extracts evidence for one resume and one job family. Python checks
references and calculates evidence strength, gap grades and demand-weighted
priority using the unchanged rubric. Grades describe resume evidence, not ability
or hiring probability; the rubric has not been empirically calibrated.

## Data boundaries

- Supabase Auth identifies the user. The existing account and resume APIs save
  and read confirmed resume data in PostgreSQL.
- Skill Gap results remain ignored local JSON under
  `backend/local_results/web_skill_gaps/`. No result-table migration is included.
- Each run records real user/resume IDs and an immutable input snapshot. Creation,
  retrieval, reuse and latest-result lookup are owner-scoped. Pre-auth experiments
  without an owner remain on disk but are inaccessible through this API.
- The shared demand snapshot comes from
  [PR #20's six-table job-analysis output](https://github.com/CS620-Microsoft-1/careergps/pull/20),
  supplied as `six_tables_split.zip`. Its counts and ratios are unchanged:
  Software Engineer N=2858 (22 skills), Data Analyst N=174 (18 skills),
  AI Engineer N=566 (23 skills).
  [Source, limitations and portable reproduction](SKILL_GAP_DEMAND_SOURCE.md)
  explain why this fixed export is not a verified 90-day market sample.
- Runtime code is in `backend/app/services/skill_gaps/`; historical experiments,
  local tests and previous run outputs are not dependencies.

## Configuration

Install backend requirements in a virtual environment and run `npm ci` in
`frontend/`. Copy the existing `.env.example` files to ignored `backend/.env`
and `frontend/.env.local`, then fill in the real project settings:

```dotenv
# backend/.env
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/postgres?sslmode=require
SUPABASE_URL=https://<project-ref>.supabase.co
CORS_ORIGINS=http://localhost:3000
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_AGENT_NAME=<resume-agent>
SKILL_GAP_FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
SKILL_GAP_FOUNDRY_AGENT_NAME=<skill-gap-agent>
```

```dotenv
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_<key>
```

The frontend key is the public publishable key, never a Supabase secret key.
Backend JWT configuration follows `backend/README.md`; projects using signing
keys do not need a legacy JWT secret. Do not commit real environment files.
The existing database schema must already be available; follow the team's
migration ownership rules instead of applying shared migrations yourself.

For real Agent calls, authenticate with `az login`. The latest non-draft Agent
version must match the checked-in
[Instructions](../../backend/app/prompts/skill_gaps/Instructions.md) and
[response Schema](../../backend/app/services/skill_gaps/data/response-format.json).
The checked version is pinned for inference. No repair or explanation call is made.

## Run locally

Windows PowerShell, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

macOS/Linux, from `backend/`:

```sh
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, from `frontend/`, on either platform:

```sh
npm run dev
```

Open http://localhost:3000, sign in and complete onboarding or upload a new
resume. Confirming Review saves the account/resume first, then opens Dashboard
and starts analysis. A failed save never starts analysis. Page navigation,
refresh and another device restore the latest matching run through the backend;
only a post-save intent or an explicit Analyze action starts a call. Analyze
again explicitly requests a fresh run. A run already queued/running is reused
even if `force` is requested.

Results are local to the backend host. Another device can restore them when it
uses the same backend host; separate backend machines do not share result files.
Use one application worker while this file-backed queue is in use. Multi-worker
or multi-instance deployment requires shared job/result storage in a later PR.

Dashboard, Career Analysis, Skill Gaps and Profile share the analysis. Existing
Supabase login, account menu, onboarding guard and profile data remain intact.
Overall career readiness, common responsibilities and action plans are not yet
computed.

## Endpoints

All `/skill-gaps/*` endpoints require a logged-in, onboarded user:

- `GET /skill-gaps/market/{job_family}`: frozen demand and provenance metadata.
- `POST /skill-gaps/runs` with `{ "job_family": "software_engineer", "force": false }`:
  load the user's active saved resume and enqueue/reuse one run. Omit `job_family`
  to use the account target role. The body does not accept resume JSON or owner IDs.
- `GET /skill-gaps/runs/latest?job_family=software_engineer`: restore the current
  user's active resume and current configuration, or return 404.
- `GET /skill-gaps/runs/{id}`: owner-only status/result polling; never calls the Agent.

## Offline tests

The normal CI command discovers the checked-in backend tests. New Skill Gaps
regressions mock the Agent and database access; no network, private data, Azure
login or shared database is required:

```sh
cd backend
python -m unittest discover -s tests -v
```

Focused backend tests, from `backend/`:

```sh
python -m unittest tests.test_skill_gap_core_contract tests.test_skill_gap_run_ownership tests.test_skill_gap_authenticated_api tests.test_skill_gap_transport_version tests.test_skill_gap_demand -v
```

Frontend controller tests, from `frontend/`:

```sh
node --test lib/skill-gap-*.test.cjs
```

On Windows activate `.venv\Scripts\Activate.ps1`; on macOS/Linux activate `.venv/bin/activate`. See the new test modules for
scoring boundaries, null/pending references, stable source IDs, authenticated
routes, user isolation, reuse/force/restart and portable demand reproduction.

## Proposed result storage contract

The [storage JSON Schema](../contracts/skill-gap-run-storage.schema.json) and
[fictional example](../contracts/skill-gap-run-storage.example.json) remain a
proposal for a later `skill_gap_runs` migration. They do not create tables or
implement result persistence in PostgreSQL. Runtime results still use local files.

The proposed record links the authenticated user, real resume ID, immutable
13-section input snapshot, demand snapshot and configuration fingerprint. Report
resume IDs now refer to the same real resume row. Scores, quotations, source
indices and pending states must remain available, rather than storing only grades.
Database ownership checks and arithmetic cannot be established by JSON Schema
alone. The database owner will review columns, JSONB, indexes and policies in the
follow-up PR.

## Offline reference-alignment replay

The local response-processing step can recover a uniquely identifiable original
quotation when the model adds an exterior ellipsis, changes only the initial case
of a prose sentence, or supplies a known wrong unit ID within the same activity.
The calculation copy uses the exact recovered original text and records each
change. Unknown IDs, cross-activity matches, ambiguous matches, changed words or
values, and other failed prerequisites remain pending. A whole row must pass the
unchanged validation gates; partial repairs are rolled back.

This does not change Agent Instructions, the response Schema, semantic labels,
scoring points/caps/grade boundaries, or demand counts/ratios. It does not fill
missing methods or decide whether a quoted operation demonstrates the right
capability. Source integrity is not semantic verification.

To compare a completed saved response without calling the Agent, run from
`backend/` with its virtual environment active:

```sh
python -m scripts.replay_skill_gap_response --run-dir "local_results/web_skill_gaps/RUN_ID" --output "local_results/reference-replay"
```

Replace `RUN_ID` with the saved run directory name and choose a new output path.
The command has no database or network access. It reads the original input,
Agent response and report, verifies unchanged demand, and writes a separate
before/after report, reference checks, adjustment audit and comparison README.
All original run files are hashed before and after; existing output paths are
refused. The web cache and original result are not replaced by this command.
The comparison reports zero new model calls and separates offline computation
time from the original inference time. Private results remain ignored by Git.

### Saved-response comparison on 2026-10-26

The user's saved AI Engineer response was recalculated with local alignment v3.
The original run and raw files stayed byte-identical. The replay made **zero new
model calls**, used no database, and took **0.034 seconds** of offline calculation;
the original model-backed run took 50.426 seconds. These are different stages,
not a measurement of faster model inference.

| Skill | Before | Evidence strength after | Evidence gap after | Grade after |
| --- | --- | ---: | ---: | --- |
| Data preparation | Pending | 0.65 | 0.35 | B |
| Model deployment and serving | Pending | 0.60 | 0.40 | B |
| Generative AI | Pending | 0.45 | 0.55 | C |

All 23 skills now pass mechanical reference checks, compared with 20 previously.
The existing 20 scored skills retain exactly the same strength, gap, grade and
priority. The new distribution is 12 B, 7 C and 4 D, with no pending references.
Forty synthetic alignment tests and five portable replay tests pass. They cover
ambiguity, same-activity boundaries, numeric and identifier preservation, atomic
rollback, audit-schema compatibility, no-network execution, raw-file preservation,
identity metadata, incompatible demand/policy rejection and output overwrite
guards. The final clean-copy backend suite passed 367 tests with eight opt-in
PostgreSQL tests skipped; no private fixtures or old experiment outputs were used.

This resolves the three quotation failures, while retaining the original Agent
categories. The previously noted method omission and broad infrastructure
judgment remain model limitations. The model-deployment grade still needs
semantic review; recovering its quotation does not prove serving experience.
The replay is a separate saved comparison, and the original web result remains
unchanged until an explicit result-update step is requested.


## Local verification on 2026-10-26

- Tested a clean source checkout without private env files, old experiments,
  ignored resume fixtures or historical run outputs: 322 backend tests passed;
  eight opt-in real PostgreSQL tests were skipped. This includes 31 new Skill
  Gaps tests. Existing Windows test cleanup and UTF-8 reads were corrected without
  changing job-analysis production behavior.
- All 22 frontend tests, TypeScript, ESLint and the Next.js 16.4.3 production build
  passed.
- Replayed the original export with the portable demand tool: all three N values
  and all 63 core-skill counts/ratios matched. The eight protected scoring,
  Instructions, schema, catalog and demand assets stayed byte-identical locally.
- With private local configuration supplied, read-only PostgreSQL connectivity,
  required resume columns, public Supabase signing keys, API health and HTTP 401
  protection were verified. The login page loaded and protected pages redirected
  to login.
- Saved Azure Agent version 28 matched the local Instructions and response schema.
  The initial preflight made no inference call; automated tests use synthetic
  accounts and a mocked Agent.
- The user subsequently completed a real AI Engineer flow: confirmed email,
  resume parsing, Review save, automatic analysis and result restoration. The
  analysis took 50.426 seconds (48.231 seconds of inference), with one Skill Gap
  model call and no repair or summary calls. This count excludes the separate
  resume-parsing Agent stage.
- The saved database resume, active resume pointer, owner, content hash and
  report IDs matched in a read-only audit. Logs contained one analysis POST and
  successful polling/latest restoration, with no duplicate Skill Gap submission.
- Twenty of 23 skills were scored (10 B, 6 C, 4 D). Data preparation, model
  deployment and generative AI remained null/pending because of an added
  ellipsis, changed capitalization and a wrong source ID respectively. Replaying
  the saved response reproduced all scores and checks; independent arithmetic
  checks found no discrepancy. No second Agent call was made during the audit.
- Known model limitations remain: a model-evaluation method was omitted, and
  AI-infrastructure evidence may be too broad. Exact-reference validation does
  not establish semantic relevance. This verifies one real AI Engineer flow,
  not live runs for all families or the PostgreSQL RLS policy matrix.

## Integration with resume progress from dev

On 2026-10-26, `origin/dev` at `3da5a2d` (PR #23) was integrated into the local
`test/skill-gaps` branch. The resume upload flow now displays the streamed
extraction, OCR and classification steps before Review. Review still saves the
confirmed resume through the account API before queuing Skill Gaps on Dashboard.
Both resume-progress and Skill Gaps types are retained in the shared API contract.

All 374 backend tests passed, with eight opt-in PostgreSQL tests skipped. All
27 frontend tests, ESLint and the production build passed, including five new
stream-client regressions for chunk decoding, authentication, errors and cancel
behavior without automatic retry. No Agent call or migration was run during this
integration. Scoring, demand, Instructions and local reference-alignment code were
preserved; previous personal run files were not changed.

The API must be restarted after syncing to expose `/resumes/analyze/stream`.
Response-processing versions are part of the result-reuse fingerprint. A saved
result from an earlier configuration stays on disk but may not be selected as
the latest result for the current configuration; page restoration does not start
a replacement model call automatically.
