# CareerGPS Backend

Python 3.12+ · FastAPI · SQLAlchemy · Alembic · PostgreSQL (hosted on Supabase). See [ADR-002](../docs/decisions/ADR-002-CareerGPS-Backend.md).

The whole team shares **one Supabase Postgres database**. There is no local database to set up.

## Setup

Python 3.12 or newer is required. On macOS or Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Paste the shared `DATABASE_URL` into `.env` (ask Abanish for it privately). `CORS_ORIGINS` can stay
as `http://localhost:3000`. Set `SUPABASE_URL` to `https://<project-ref>.supabase.co` (the project ref
is the part after `postgres.` in `DATABASE_URL`); without it, endpoints that need login return 503.
Then check:

```bash
python -m app.db.check_connection   # should print "Connected ✅"
alembic current                     # should print the latest revision with "(head)"
```

> `.env` holds the database password. **Never commit it** or paste it into chat, PRs or issues.
> If the password contains `@ : / # ? %`, it breaks the URL. Use letters and numbers only.

## Resume parsing environment

The résumé feature needs both Python packages and system-installed tools. Installing only
`requirements.txt` is not enough for scanned PDFs.

### Windows quick setup

Install these applications first:

- [Python 3.12 or newer](https://www.python.org/downloads/windows/) (64-bit)
- [Tesseract OCR](https://tesseract-ocr.github.io/tessdoc/Installation.html) with English data
  (64-bit, required)
- [Ghostscript](https://ghostscript.com/releases/gsdnld.html) (64-bit, recommended for the
  broadest PDF compatibility)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli-windows)

Then open PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

OCRmyPDF checks the Windows Registry and standard Program Files locations for Tesseract and
Ghostscript. The backend also adds Tesseract's usual `C:\Program Files\Tesseract-OCR` directory
when it exists. Open a new PowerShell window after installation, then verify the environment:

```powershell
python --version
tesseract --version
ocrmypdf --version
az version
```

If `tesseract` is not on `PATH`, verify the default installation directly:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

When Ghostscript is on `PATH`, `gswin64c --version` verifies it. A standard Program Files
installation can still be detected by OCRmyPDF through the Windows Registry.

Then complete the `.env`, Azure RBAC, Agent prompt, and run steps below.

### macOS quick setup

Install [Homebrew](https://brew.sh/) first, then install Python, OCRmyPDF's system dependencies,
and Azure CLI. The current Homebrew Azure CLI package requires macOS 13 or newer.

```bash
brew update
brew install python@3.12
brew install --only-dependencies ocrmypdf
brew install azure-cli

cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Homebrew's OCRmyPDF dependencies include Tesseract, Ghostscript, and English OCR language data.
The Python module used by CareerGPS is still installed inside `.venv` from `requirements.txt`.
Additional OCR languages are optional and can be installed with `brew install tesseract-lang`.

Verify the macOS environment before starting the API:

```bash
python --version
tesseract --version
gs --version
ocrmypdf --version
az version
```

Then complete the `.env`, Azure RBAC, Agent prompt, and run steps below.

### What each pipeline step uses

| Pipeline step | Required tool | Purpose |
|---|---|---|
| Receive an upload | FastAPI + `python-multipart` | Accept one PDF or DOCX up to 10 MB |
| Native PDF extraction | PyMuPDF | Read selectable text and identify pages with too little text |
| DOCX extraction | python-docx | Read paragraphs and table cells |
| Scanned PDF fallback | OCRmyPDF | Run OCR only when PDF pages need it |
| OCR engine | Tesseract OCR with English language data | Recognize text in page images |
| PDF compatibility for OCR | Ghostscript (recommended) | Provide OCRmyPDF's broadest PDF support; the current PDF output can also use pypdfium2 |
| Résumé classification | Existing Microsoft Foundry Agent | Convert extracted text to the fixed résumé JSON contract |
| Local Azure authentication | Azure CLI + `azure-identity` | Let `DefaultAzureCredential` use the developer's Azure identity |
| JSON validation | Pydantic | Reject unsupported Agent output and normalize compatible legacy fields |
| Review UI | Next.js frontend | Show extracted text and editable structured results |

No OCR model weights or Foundry model are stored in this repository. `requirements.txt` records
the allowed Python package version ranges; every developer installs those packages and system
tools locally.

### 1. Install the Python packages

Activate `backend/.venv`, then run:

```bash
python -m pip install -r requirements.txt
python -c "import pymupdf, docx, ocrmypdf; print('Resume dependencies are available')"
```

### 2. Install the OCR system tools

Install:

- [Tesseract OCR](https://tesseract-ocr.github.io/tessdoc/Installation.html), including the
  English (`eng`) language data.
- [Ghostscript](https://ghostscript.com/releases/gsdnld.html), recommended for the broadest PDF
  compatibility.

Both are external applications and are not installed by `pip`. On Windows, OCRmyPDF checks the
Registry and standard Program Files locations, and the backend additionally checks Tesseract's
default `C:\Program Files\Tesseract-OCR` directory.

Verify the installations:

```powershell
tesseract --version
ocrmypdf --version
```

When Ghostscript is on `PATH`, use `gswin64c --version` on Windows or `gs --version` on macOS and
Linux.

### 3. Install Azure CLI and authenticate

Install the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then use your
own Azure account:

```bash
az login
az account show
```

`az login` proves the caller's identity; it does not grant access by itself. An Azure administrator
must assign the account an appropriate Microsoft Foundry RBAC role:

- `Foundry Agent Consumer`: least privilege for calling the existing Agent endpoint.
- `Foundry User`: broader access for developers who must open, test, or edit the Agent.

Prefer Agent or Project scope instead of Subscription scope. Never share Azure accounts, access
tokens, CLI credential folders, or service-principal secrets. Calls made by an authorized team
member consume the quota and billing of the Azure resource that hosts the Agent. See the
[Microsoft Foundry RBAC documentation](https://learn.microsoft.com/azure/ai-foundry/concepts/rbac-ai-foundry).

### 4. Configure `backend/.env`

Copy `.env.example` to `.env` and replace every placeholder locally:

| Variable | Used by | Required value |
|---|---|---|
| `DATABASE_URL` | Existing CareerGPS database features | Shared Supabase PostgreSQL connection string |
| `CORS_ORIGINS` | Browser access to FastAPI | Frontend origins, normally `http://localhost:3000` |
| `FOUNDRY_PROJECT_ENDPOINT` | Résumé classification | The existing Foundry Project endpoint |
| `FOUNDRY_AGENT_NAME` | Résumé classification | The existing résumé Agent name |

`backend/.env` is ignored by Git. Never force-add it, paste it into an issue, or include it in a
pull request. The endpoint and Agent name identify the target but do not bypass Azure RBAC.

### 5. Synchronize the Foundry Agent instructions

The Agent instructions and exact JSON contract are maintained in
`docs/resume-classifier-agent-prompt.md`. Copy the latest version into the existing Foundry Agent
before testing. Updating the Markdown file in Git does not automatically update the remote Agent.
`docs/resume-classification-example.json` is a locally validated example of the same contract.

### 6. Run and verify the pipeline

Start the backend from `backend/`:

```bash
uvicorn app.main:app --reload
```

Start the frontend separately by following `frontend/README.md`, then upload a PDF or DOCX from
the onboarding page. For a direct live smoke test using synthetic files:

```bash
python tests/manual_resume_smoke.py path/to/resume.pdf path/to/resume.docx
```

`POST /resumes/analyze` creates a controlled temporary file, extracts the text, runs OCR only when
needed, calls the existing Foundry Agent, validates the JSON, and returns the result to the browser.
The temporary file is deleted after the request. During this test phase, the original résumé,
extracted text, edited classification, and review result are not written to PostgreSQL or Supabase
Storage.

## Project layout

```text
app/
├── main.py                  # FastAPI app: CORS + routers (entry point for uvicorn)
├── core/
│   ├── config.py            # Settings read from .env (database, CORS, Supabase Auth, Foundry)
│   ├── options.py           # career goal choices (target roles, experience levels); mirrors the frontend
│   └── security.py          # verifies Supabase Auth access tokens (JWTs)
├── api/
│   ├── deps.py              # get_db, get_current_user (token), get_current_db_user (token + users row)
│   └── routes/
│       ├── health.py        # GET /health, GET /health/db
│       ├── me.py            # POST /me, GET /me, PATCH /me/profile
│       └── resumes.py       # POST /resumes/analyze (no persistence)
├── db/
│   ├── base.py              # SQLAlchemy Base; every model inherits from it
│   ├── session.py           # engine + SessionLocal, built from settings
│   └── check_connection.py  # connectivity test
├── models/
│   ├── __init__.py          # import every model here so Alembic can see it
│   ├── job_posting.py       # job_postings + ingest_runs
│   ├── profile.py
│   └── user.py              # id = Supabase Auth account id
├── schemas/
│   ├── me.py                # /me requests and responses
│   └── market.py            # NormalizedPosting, MarketProfile
└── services/
    ├── accounts.py          # creates and updates users + profiles
    └── postings/            # job board adapters (Greenhouse, Ashby, Lever) and daily ingest
data/
├── companies.yaml           # job boards to ingest (generated by probe_boards.py, then reviewed)
└── company_candidates.yaml  # companies for probe_boards.py to look for
scripts/
├── ingest_postings.py       # daily job posting ingest
└── probe_boards.py          # find which companies have a public job board
migrations/
├── env.py                   # Alembic setup: reads settings, loads models
└── versions/                # migration files (committed, never edited once applied)
tests/                       # unittest; run by CI on every PR to dev, no DB or network needed
```

## Run the API

```bash
uvicorn app.main:app --reload            # http://localhost:8000
uvicorn app.main:app --reload --port 8010   # if port 8000 is already in use
```

| URL | What it shows |
|---|---|
| `/health` | `{"status": "ok"}` when the API is running (no database access) |
| `/health/db` | `{"status": "ok", "database": "connected"}`, or **503** if the database is unreachable |
| `POST /me` | Finish sign-up: creates the `users` and `profiles` rows for the logged-in account. **409** if they exist |
| `GET /me` | `{user, profile}` for the logged-in account; both `null` until `POST /me` succeeds |
| `PATCH /me/profile` | Update `location`. **403** until `POST /me` succeeds |
| `/docs` | Interactive API docs (Swagger UI), generated from the code |
| `/openapi.json` | The API contract; the source of truth for frontend types (ADR-002) |
| `/resumes/analyze` | Temporary PDF/DOCX extraction, OCR fallback and Foundry classification |

### Authentication

Sign-up, login and logout happen in the frontend with Supabase Auth; the API never sees passwords.
The frontend sends the Supabase access token as `Authorization: Bearer <token>`. The API checks its
signature (Supabase's public signing keys, or `SUPABASE_JWT_SECRET` on legacy projects), expiry,
audience and issuer. Missing or invalid token → **401**.
The shared project uses JWT signing keys (ES256, checked 2026-10-14), so leave `SUPABASE_JWT_SECRET`
unset.

Supabase Auth settings (dashboard, not migrations; record any change here):

| Setting | Value (checked 2026-10-14) |
|---|---|
| Email sign-up | On, **Confirm email** on |
| Site URL | `http://localhost:3000` |
| Sign-ups and sign-ins | 30 requests / 5 min per IP |
| Token verifications | 30 requests / 5 min per IP |
| Token refreshes | 150 requests / 5 min per IP |
| Emails | 2 / hour for the whole project (built-in sender; only delivers to members of the Supabase organization). Create test users in Authentication → Users with auto-confirm instead of signing up |

- `Depends(get_current_user)`: the Supabase account (id, email). Use for `/me` sign-up.
- `Depends(get_current_db_user)`: also requires the `users` row; **403** if sign-up isn't finished.
  Use this for everything else.
- Never log tokens.

New endpoints go in their own router under `app/api/routes/` and are registered in `app/main.py`.
Use `db: Session = Depends(get_db)` for database access; keep business logic out of the route
function. Only origins listed in `CORS_ORIGINS` can call the API from a browser; never use `*`.

The frontend calls each router from a file with the same name in `frontend/lib/api/`
(`routes/health.py` ↔ `lib/api/health.ts`). When you add a router, add its frontend file too.
The frontend finds the API through `NEXT_PUBLIC_API_URL` in `frontend/.env.local`; if you run
the API on another port, update it there and restart `npm run dev`.

## Run the tests

```bash
python -m unittest discover -s tests -v
```

To run a live smoke test against the configured Foundry Agent using synthetic files:

```bash
python tests/manual_resume_smoke.py path/to/resume.pdf path/to/resume.docx
```

## Collect job market data

The Market Intelligence feature uses postings from the public Greenhouse, Ashby and Lever job
boards of the companies in `data/companies.yaml` (see ADR-003). No credentials are needed. The
`job_postings` and `ingest_runs` tables must exist (`alembic upgrade head`).

```bash
python -m scripts.ingest_postings                      # every board, about 2 minutes
python -m scripts.ingest_postings --source ashby       # one source
python -m scripts.ingest_postings --company stripe     # one company (name or slug); repeatable
```

Each board is fetched once, one second apart, and synced in its own transaction. Postings that
are no longer listed are marked closed, not deleted, so statistics can cover a date window.
A failed board is recorded in `ingest_runs` and does not stop the run.

**Run it once a day, starting as early as possible.** The job boards only return postings that
are open today, so history begins on the first run. Locally, a cron entry works
(`crontab -e`; replace the path):

```text
0 7 * * * cd /path/to/careergps/backend && .venv/bin/python -m scripts.ingest_postings >> ingest.log 2>&1
```

To add companies, add them to `data/company_candidates.yaml` and run
`python -m scripts.probe_boards`. It prints the boards it finds; `--write` replaces
`data/companies.yaml`. Check each match before committing, since a slug can belong to a
different company with the same name.

## Changing the schema

1. Edit or add a model in `app/models/` (and import new models in `app/models/__init__.py`).
2. Generate a migration:
   ```bash
   alembic revision --autogenerate -m "describe the change"
   ```
3. **Review the generated file.** Autogenerate treats a rename as drop + add (data loss) and ignores RLS, triggers and functions; add those by hand.
4. Preview the SQL without touching the database: `alembic upgrade head --sql`
5. Open a PR. The migration is reviewed like any other code.
6. **After the PR is merged into `dev`**, one person runs `alembic upgrade head` from an up-to-date `dev`.

## Shared database rules

1. **Schema changes only go through Alembic.** Never create or alter tables in the Supabase dashboard. Viewing and editing rows there is fine.
2. **Never edit a migration that has been applied.** Write a new one.
3. **Only apply migrations from `dev`, after the PR is merged, by one person.** Never from a feature branch: a migration may still change in review, and applied migrations must never be edited (rule 2). Announce it in the team chat.
4. **No `alembic downgrade` on the shared database** without telling the team first. It can drop tables and their data.
5. **No real personal data** until authentication is in place. Use fake test users.
6. **Enable RLS on every new table** in its migration (`ALTER TABLE <name> ENABLE ROW LEVEL SECURITY`). The Supabase Data API is disabled; RLS is a second layer of protection.
7. **If `.env` leaks**, reset the database password in Supabase (Project Settings → Database) and share the new URL privately.

## Troubleshooting

| Error                                                | Likely cause                                                            |
| ---------------------------------------------------- | ----------------------------------------------------------------------- |
| `validation error for Settings` … `database_url`     | `.env` missing or has no `DATABASE_URL`                                 |
| `failed to resolve host`                             | Placeholder left in `.env`, or `@` in the password                      |
| `No module named 'app'`                              | Run commands from `backend/`, not the repo root                         |
| Connection refused / timeout after a quiet week      | Free Supabase project paused; resume it from the dashboard              |
| `Multiple head revisions`                            | Two migrations branched from the same parent; run `alembic merge heads` |
| VS Code: `Import "sqlalchemy" could not be resolved` | Select `backend/.venv/bin/python` as the interpreter                    |
| `address already in use` when starting uvicorn       | Another app uses that port; add `--port 8010`                           |
| Browser: `blocked by CORS policy`                    | Add the frontend's origin to `CORS_ORIGINS` in `.env` and restart       |
| `tesseract` or `gswin64c` is not recognized          | Install the OCR system tool and add its executable directory to `PATH`  |
| Azure authentication failed                          | Run `az login`, select the correct account and restart the backend       |
| Foundry request returns 403                          | Ask an administrator to assign Foundry Agent Consumer or Foundry User   |
| Foundry Agent returned an invalid result             | Synchronize the checked-in Agent prompt and retry with the same résumé   |
