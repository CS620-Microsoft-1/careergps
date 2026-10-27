# CareerGPS

[![Backend baseline checks](https://github.com/CS620-Microsoft-1/careergps/actions/workflows/backend-baseline-tests.yml/badge.svg?branch=dev)](https://github.com/CS620-Microsoft-1/careergps/actions/workflows/backend-baseline-tests.yml)

An agentic career-intelligence platform that helps students see how competitive they are for a target role and
what to do next. CareerGPS reads a student's résumé, compares it with real job-market data, ranks the skill gaps,
and turns them into an action plan.

## Features

| Area | Status |
| --- | --- |
| Sign-up / login with Supabase Auth (email confirmation), onboarding, profile | Working |
| Résumé parsing: PDF/DOCX extraction, OCR fallback for scanned pages, classification by a Microsoft Foundry Agent, editable review, saved to the user's account | Working |
| Job-market data: daily ingest of public Greenhouse, Ashby and Lever job postings; job-description field extraction by a Foundry Agent | Working |
| Skill-gap analysis: résumé evidence scored against market demand, with a demand-weighted match score | Working (runs are local JSON on the backend host) |
| Destinations: compare one résumé against several target roles | Working |
| Resources: courses, student orgs, certifications and projects matched to each gap | Working (static catalogs) |
| Action plan: saved resources in order, biggest gap first | Working (plans are local JSON on the backend host) |
| Ask CareerGPS Copilot | Planned |
| `plan_items` and `skill_gap_runs` tables | Migrated, not yet used by the API |

The analysis runs as four agents in order: **Student Profile → Market Intelligence → Gap Analysis → Action**.

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, shadcn/ui, Zod, React Hook Form |
| Backend | Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| Database and auth | PostgreSQL and Supabase Auth (one shared team project) |
| AI | Microsoft Foundry Agents via `azure-ai-projects` and `azure-identity` |
| Document processing | PyMuPDF, python-docx, OCRmyPDF + Tesseract, Ghostscript |
| CI | GitHub Actions (backend unit tests on PRs to `dev`) |

Each choice is explained in the [architecture decision records](docs/decisions/).

## Architecture

```text
Next.js frontend ──HTTP/JSON──▶ FastAPI backend ──▶ Supabase PostgreSQL
  (localhost:3000)               (localhost:8000)  ├─▶ Supabase Auth (verifies login tokens)
        │                                          ├─▶ Microsoft Foundry Agents (résumé, job description,
        │                                          │   skill gap, certification)
        │                                          └─▶ Greenhouse / Ashby / Lever public job-board APIs
        └──▶ Supabase Auth (sign-up / login)
```

- The frontend calls the API only through `frontend/lib/api/`, with one file per backend area.
- Market statistics are computed with SQL over stored postings. LLMs only extract fields or explain results that
  were already computed ([ADR-003](docs/decisions/ADR-003-Career-Market-Data-Sources.md)).

## Project structure

```text
careergps/
├── backend/               FastAPI service
│   ├── app/               api/routes, core config, db, models, schemas, services
│   ├── data/              company job-board lists and the resource, certification and project catalogs
│   ├── migrations/        Alembic migrations
│   ├── scripts/           job-posting ingest, board probe, job-analysis worker, demand snapshot
│   └── tests/             unittest suite (no DB or network needed)
├── frontend/              Next.js app
│   ├── app/               routes: auth, onboarding (setup), dashboard (home), gaps, resources, plan, destinations, profile
│   ├── components/        UI primitives, layout, auth, setup, one folder per page
│   ├── lib/               API client, Supabase client, navigation, validation, skill-gap helpers
│   └── types/             shared TypeScript types
├── docs/
│   ├── contracts/         skill-gap run storage schema and example
│   ├── decisions/         ADR-001 frontend, ADR-002 backend, ADR-003 market data sources, JPA storage schema
│   ├── infrastructure/    domain setup
│   ├── specs/             SPEC-001 sign-up and login
│   ├── supabase/          email templates
│   ├── testing/           Supabase database test plan, skill-gap test guides
│   └── resume-classifier-agent-prompt.md   Foundry Agent instructions and JSON contract
└── .github/workflows/     CI
```

## Getting started

### Prerequisites

- Python 3.12+ and Node.js 20.9+
- Tesseract OCR (with English data) and Ghostscript, for scanned résumés
- Azure CLI, signed in with an account that has a Microsoft Foundry RBAC role
- The shared `DATABASE_URL`, from the database owner (share it privately)

### Backend

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # fill in DATABASE_URL and FOUNDRY_* values
az login
python -m app.db.check_connection # should print "Connected ✅"
uvicorn app.main:app --reload     # http://localhost:8000 (API docs at /docs)
```

### Frontend

```bash
cd frontend
npm ci
cp .env.example .env.local        # NEXT_PUBLIC_API_URL, defaults to http://localhost:8000
npm run dev                       # http://localhost:3000
```

The **backend status badge** in the profile menu and on the Profile page shows whether the app can reach the API and the database.

Windows setup, Foundry access, and troubleshooting are covered in the [backend README](backend/README.md) and the
[frontend README](frontend/README.md).

## Configuration

| File | Variable | Purpose |
| --- | --- | --- |
| `backend/.env` | `DATABASE_URL` | Supabase PostgreSQL connection (session pooler) |
| | `CORS_ORIGINS` | Frontend origins allowed to call the API (never `*`) |
| | `SUPABASE_URL` | Supabase project, used to verify login tokens |
| | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_AGENT_NAME` | Résumé classification Agent |
| | `SKILL_GAP_FOUNDRY_PROJECT_ENDPOINT`, `SKILL_GAP_FOUNDRY_AGENT_NAME` | Skill gap evidence Agent |
| | `JOB_ANALYSIS_*` | Job-description extraction Agent and its local queue |
| | `CERTIFICATION_FOUNDRY_PROJECT_ENDPOINT`, `CERTIFICATION_FOUNDRY_AGENT_NAME` | Certification Agent (optional; falls back to the catalog) |
| `frontend/.env.local` | `NEXT_PUBLIC_API_URL` | Backend URL (public: never put secrets here) |
| | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase Auth (publishable key only) |

See `backend/.env.example` and `frontend/.env.example` for every variable.

Never commit `.env` or `.env.local`.

## Testing

```bash
cd backend && python -m unittest discover -s tests -v   # also runs in CI
cd frontend && npm test && npm run lint && npm run typecheck && npm run build
```

`backend/tests/manual_resume_smoke.py` runs a live test against the Foundry Agent. It is not part of CI.

## Data collection

```bash
cd backend
python -m scripts.ingest_postings          # all boards in data/companies.yaml; run once a day
python -m scripts.probe_boards             # find job boards for companies in data/company_candidates.yaml
```

Job-description extraction (`scripts.job_posting_analysis_worker`) and market demand snapshots
(`scripts.demand_snapshot`) are covered in the [backend README](backend/README.md#job-posting-analysis) and
[docs/testing/SKILL_GAP_DEMAND_SOURCE.md](docs/testing/SKILL_GAP_DEMAND_SOURCE.md).

## Contributing

- Branch off `dev` and open pull requests into `dev`. `main` is the release branch.
- Use Conventional Commits with a scope, for example `feat(backend): ...`, `fix(frontend): ...`, `docs: ...`.
- **Database changes only go through Alembic migrations.** Never edit an applied migration. Enable row-level
  security on every new table. Only the database owner applies migrations to the shared database, after merge.
- Frontend screens must work from 320px to 2560px wide and with a larger browser font. See the responsive rules in
  the [frontend README](frontend/README.md#responsive-rules).

## Documentation

- [Backend README](backend/README.md): setup, résumé pipeline, schema workflow, database rules
- [Frontend README](frontend/README.md): setup, API client, responsive rules, Copilot
- [Architecture decision records](docs/decisions/)
- [Sign-up and login spec](docs/specs/SPEC-001-signup-and-login.md)
- [Supabase database test plan](docs/testing/SUPABASE_DATABASE_TEST_PLAN.md)
- [Skill gaps: local web test](docs/testing/SKILL_GAP_WEB_LOCAL.md) and
  [demand source](docs/testing/SKILL_GAP_DEMAND_SOURCE.md)
- [Résumé classifier prompt](docs/resume-classifier-agent-prompt.md)
