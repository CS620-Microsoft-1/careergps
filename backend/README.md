# CareerGPS Backend

Python 3.12+ · FastAPI · SQLAlchemy · Alembic · PostgreSQL (hosted on Supabase). See [ADR-002](../docs/decisions/ADR-002-CareerGPS-Backend.md).

The whole team shares **one Supabase Postgres database** for application data.
The current JD analysis queue and results are stored locally, as described below.

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
as `http://localhost:3000`. Then check:

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
│   └── config.py            # Database, CORS and Foundry settings read from .env
├── api/
│   ├── deps.py              # get_db: one DB session per request, always closed
│   └── routes/
│       ├── health.py        # GET /health, GET /health/db
│       └── resumes.py       # POST /resumes/analyze (no persistence)
├── db/
│   ├── base.py              # SQLAlchemy Base; every model inherits from it
│   ├── session.py           # engine + SessionLocal, built from settings
│   └── check_connection.py  # connectivity test
├── models/
│   ├── __init__.py          # import every model here so Alembic can see it
│   ├── job_posting.py       # job_postings + ingest_runs
│   ├── resume.py            # resumes + experiences, educations, projects, achievements, skills
│   └── user.py              # users (id = the Supabase Auth account id)
├── schemas/
│   └── market.py            # NormalizedPosting, MarketProfile
└── services/
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
| `/docs` | Interactive API docs (Swagger UI), generated from the code |
| `/openapi.json` | The API contract; the source of truth for frontend types (ADR-002) |
| `/resumes/analyze` | Temporary PDF/DOCX extraction, OCR fallback and Foundry classification |

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

## Job posting analysis

### JD quick start on a new computer

This sets up the local backend to call the **existing** Azure Agent named
`job-analysis-agent`, fixed at **version `13`**. The extracted result keeps all **28 fields**
from `app/schemas/job_posting_analysis_v13.json`. Only `locations`, `role_overview`,
`responsibilities`, `qualifications`, `job_conditions` and `compensation` retain nested
structures and evidence. Other scalar fields are direct strings or `null`; `benefits` is a
string or `null`, and `other_relevant_information` is a string array. This repository contains
the local output contract and client code; it does not create an Azure Agent or reproduce
its full remote Instructions/model configuration in a new Azure project.

Use a Git checkout containing this feature. Live testing requires access to the existing
Foundry project and to an already-populated Supabase `job_postings` table. For JD setup,
leave the deployed Agent unchanged and use the existing tables. The résumé Instructions
synchronization, scraper and Alembic migration steps are separate workflows. JD analysis
does not require Tesseract or Ghostscript system tools.

#### 1. Install the local Python environment

Run from `backend/` in the checkout. On macOS/Linux:

```bash
cd /path/to/careergps/backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
cd C:\path\to\careergps\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Python 3.12 or newer is required. An existing activated backend environment can also be
used; its folder name does not have to be `.venv`. Keep subsequent commands in `backend/`.

#### 2. Run offline tests first

This command works in Bash/zsh and PowerShell. It supplies a dummy database URL and blank
Azure endpoints only for this Python process, so it does not require Azure login, a real
Supabase connection string, or a `.env` file. Tests use synthetic inputs, mocked Agents and
temporary local databases; they neither call the remote Agent nor write to Supabase.

```text
python -c "import os, unittest; os.environ.update(DATABASE_URL='postgresql+psycopg://tester:not-a-real-password@127.0.0.1:1/test', JOB_ANALYSIS_PROJECT_ENDPOINT='', JOB_ANALYSIS_ADMIN_TOKEN='', FOUNDRY_PROJECT_ENDPOINT='', FOUNDRY_AGENT_NAME=''); unittest.main(module=None, argv=['unittest', 'discover', '-s', 'tests', '-t', '.', '-v'])"
```

Success ends with `OK`. The full suite includes the five JD test modules plus the existing
backend tests. The reported test count can change as scenarios are added; use the command
result for the current total. Git metadata is needed for repository configuration checks.

#### 3. Configure access for a live test

Copy `.env.example` to `.env` if `.env` does not already exist. Edit these JD settings locally:

| Setting | What to provide |
|---|---|
| `DATABASE_URL` | Existing shared Supabase PostgreSQL connection string, obtained privately |
| `JOB_ANALYSIS_PROJECT_ENDPOINT` | Project endpoint supplied by the owner of the existing version 13 Agent; replace all placeholders |
| `JOB_ANALYSIS_TIMEOUT_SECONDS` | `600`, unless the owner specifies another timeout |
| `JOB_ANALYSIS_LOCAL_DIR` | Base directory, normally `local_exports/job_analyses`; the pipeline always adds `/v13` for its queue and results |
| `JOB_ANALYSIS_ADMIN_TOKEN` | The one-off acceptance command generates its own temporary token; set a private token here when serving the API separately |

The project endpoint has the form
`https://<resource-name>.services.ai.azure.com/api/projects/<project-name>`.
The Agent name/version are already fixed in the code. Résumé `FOUNDRY_*` settings are not
needed for JD analysis. Do not print or share the database URL or management token.

Install [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) if needed, then:

```text
az login
az account show --query name -o tsv
```

Use an account with permission to invoke the existing Agent. Ask the project owner for
access; login alone does not grant it. The shared [Azure authentication and RBAC notes](#3-install-azure-cli-and-authenticate)
also apply to JD calls. Keep all commands on your own computer; no new Azure deployment,
Agent update or database migration is part of this quick start.

#### 4. Choose an existing JP ID with a read-only query

The following command prints up to five current IDs and titles. It uses the protected
read-only source, makes no Agent calls and does not enqueue jobs:

```text
python -c "from itertools import islice; from app.db.session import SessionLocal; from app.services.job_posting_analysis_pipeline import ReadOnlyJobPostingSource; source=ReadOnlyJobPostingSource(SessionLocal); [print(job_id, source.get_posting(job_id)['title']) for job_id in islice(source.iter_ids(batch_size=5), 5)]"
```

Copy an ID from the output, or use another ID known to exist in this same database. If the
list is empty, ask the database owner about available postings before continuing.

#### 5. Run one live acceptance request

**This command sends one real analysis request to version 13 and consumes Azure model
usage.** Supabase access stays read-only; analysis state and files are saved locally. Each
run creates a fresh directory and therefore repeats the model request even for the same
posting. It does not change the Agent definition or schema.

Replace `PASTE_EXISTING_JOB_UUID_HERE` in the code below with the ID selected in step 4.
For macOS/Linux, paste the complete command. For PowerShell, save just the Python content between `python - <<'PY'` and the final `PY`
as `backend/local_tests/accept_jd_v13.py` (create `local_tests/` if needed), then run
`python local_tests/accept_jd_v13.py` from `backend/`. That helper remains ignored by Git.

```bash
python - <<'PY'
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import UUID, uuid4

job_id = "PASTE_EXISTING_JOB_UUID_HERE"
backend = Path.cwd()
if not (backend / "app" / "main.py").is_file():
    raise SystemExit("Run this command from backend/.")
sys.path.insert(0, str(backend))

folder = (backend / "local_exports" / f"acceptance_v13_{uuid4().hex[:8]}").resolve()
folder.mkdir(parents=True)
# Set overrides before the first app import/settings read. The .env file is unchanged.
token = secrets.token_urlsafe(32)
os.environ["JOB_ANALYSIS_LOCAL_DIR"] = str(folder)
os.environ["JOB_ANALYSIS_ADMIN_TOKEN"] = token
print("Directory:", folder, flush=True)

try:
    try:
        job_id = str(UUID(job_id))
    except ValueError:
        raise SystemExit("Replace job_id with an existing UUID from step 4.")

    from app.core.config import get_settings

    endpoint = get_settings().job_analysis_project_endpoint or ""
    if not endpoint.strip() or "<" in endpoint or ">" in endpoint:
        raise SystemExit("Set JOB_ANALYSIS_PROJECT_ENDPOINT in .env first.")

    from fastapi.testclient import TestClient
    from app.api.deps import get_job_analysis_pipeline
    from app.main import app
    from app.services.job_posting_analysis_agent import AGENT_VERSION
    from app.services.job_posting_analysis_pipeline import JobPostingNotFoundError

    assert AGENT_VERSION == "13"
    pipeline = get_job_analysis_pipeline()
    try:
        posting = pipeline.get_posting(job_id)
    except JobPostingNotFoundError:
        raise SystemExit("Job ID not found. No Agent request was sent; choose another ID.")

    (folder / "input.json").write_text(
        json.dumps(posting, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Company:", posting["company_name"], flush=True)
    print("Job:", posting["title"], flush=True)
    print("Calling version 13; please wait...", flush=True)

    # TestClient runs the real FastAPI route in-process; uvicorn is not needed.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/job-postings/{job_id}/analyze",
            headers={"X-Job-Analysis-Token": token},
            json={"force": False},
        )

    response_file = folder / "response.txt"
    response_file.write_text(response.text, encoding="utf-8")
    print("HTTP:", response.status_code)
    try:
        result = response.json()
    except ValueError:
        raise SystemExit(f"Response is not JSON. Inspect {response_file}")

    print("Status:", result.get("status"))
    print("Error:", result.get("error_message") or result.get("detail") or "")
    if response.status_code != 200 or result.get("status") != "succeeded":
        raise SystemExit("Acceptance failed. Keep this directory for diagnosis.")

    output = folder / "v13" / "results" / f"{job_id}.json"
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert len(saved) == 28, "Expected 28 output fields."
    assert saved["id"] == job_id, "Posting ID mismatch."
    assert saved["benefits"] is None or isinstance(saved["benefits"], str), (
        "Expected benefits string or null."
    )
    assert saved == result["structured_data"], "File/API result mismatch."
    print("Fields:", len(saved))
    print("Result:", output)
    print("Acceptance: PASSED")
except Exception as error:
    # Avoid exposing raw database/SDK exceptions or credentials.
    print("Stopped:", type(error).__name__)
    print("Inspect local files in:", folder)
    raise SystemExit(1)
PY
```

Expected success:

```text
HTTP: 200
Status: succeeded
Error:
Fields: 28
Result: .../v13/results/<job-id>.json
Acceptance: PASSED
```

Keep `input.json` (the preflight JP), `response.txt` (the API response), and
`v13/results/<job-id>.json` in the printed directory for content/evidence review. A local
`v13/queue.sqlite3` also records status and safe errors. `succeeded` confirms that the current
local checks passed; useful-information coverage and requirement meaning still need sample
review. This is an in-process API test; testing a separately hosted HTTP server is a
separate step.

For a persistent local HTTP server, configure `JOB_ANALYSIS_ADMIN_TOKEN` in `.env` with a
private value (generate one locally with `python -c "import secrets; print(secrets.token_urlsafe(32))"`),
then follow [Run the API](#run-the-api) and supply `X-Job-Analysis-Token` when calling the JD
endpoint. These live commands do not run automatically during installation or offline tests.

### JD implementation and behavior

The JD implementation follows the résumé feature's route/schema/Agent/pipeline layout:

| File | Responsibility |
|---|---|
| `app/api/routes/job_postings.py` | HTTP submission, authorization and error responses |
| `app/schemas/job_posting_analysis.py` | Request/response models and strict JSON/schema validation |
| `app/schemas/job_posting_analysis_v13.json` | Active 28-field version 13 output contract; the v10 schema remains as a historical reference |
| `app/services/job_posting_analysis_agent.py` | Fixed Agent invocation and local evidence/compensation checks |
| `app/services/job_posting_analysis_pipeline.py` | Read-only JP source, orchestration and disabled future-save boundary |
| `app/services/local_job_analysis_store.py` | Local queue/results, heartbeats and interruption recovery |
| `scripts/job_posting_analysis_worker.py` | Batch processing and queue-only submission |

HTTP requests and the worker share the same pipeline and validation. The five JD test
modules cover Agent/validation, pipeline/source, store/recovery, HTTP and worker/CLI.

The JD pipeline reads all 25 fields from an existing `job_postings` row, calls
`job-analysis-agent` version `13`, validates the response, and saves its unchanged 28-field
JSON locally. Each posting uses an independent Azure conversation with a default 600-second
request timeout and no SDK retries. The request does not override the deployed Agent's
instructions, model, reasoning or response format.

Source reads use short PostgreSQL transactions with `SET TRANSACTION READ ONLY` and a
connection-scoped SELECT guard. Sessions close before Agent calls. This restriction applies
to JD analysis; the existing scraper still has its own source-data writes. JD analysis does
not query or write `job_postings_analyses`, `ingest_runs` or another cloud result/state table.

Configure these independent JD settings using the placeholders in `.env.example`:

| Setting | Purpose |
|---|---|
| `JOB_ANALYSIS_PROJECT_ENDPOINT` | Existing Foundry project hosting version 13 |
| `JOB_ANALYSIS_TIMEOUT_SECONDS` | Agent request timeout, default 600 |
| `JOB_ANALYSIS_ADMIN_TOKEN` | Private server-only HTTP management token; blank disables submission |
| `JOB_ANALYSIS_LOCAL_DIR` | Base directory; relative paths resolve from `backend/`, and the pipeline always adds `/v13` |

Azure authentication uses the caller's identity. Never put the management token or database
credentials in frontend code or `NEXT_PUBLIC_*` variables. Normal API requests and workers
make real Azure calls and consume model usage; automated tests inject a fake Agent.

### Local storage and future Supabase save interface

The default base directory is `backend/local_exports/job_analyses/`, ignored by Git.
The pipeline always adds the version subdirectory, including when `JOB_ANALYSIS_LOCAL_DIR`
points to an explicitly configured older directory:

```text
job_analyses/
  v13/
    queue.sqlite3           # v13 local queue, ownership, last result and safe errors
    results/<job-id>.json    # complete 28-field JSON; evidence in six complex fields
```

Existing v10 files and queues are retained without conversion or automatic reanalysis.
Do not add `/v13` to the configured base yourself. A new v13 queue does not reuse earlier
results or states, so starting a worker will discover all source jobs missing from this new
queue and can trigger a full backfill. Stop older workers/API processes before switching;
run offline tests first and start live processing only when ready.

The queue survives restarts and permits one current attempt per posting. Failed refreshes
retain the previous successful result. JSON writes use a temporary file and replacement;
SQLite remains the committed source of truth during interruption recovery.

`app/services/job_posting_analysis_pipeline.py` reserves the internal function
`save_analysis_to_supabase(job_posting_id=..., structured_data=...)` for the future
`job_postings_analyses` destination. It always raises `SupabaseAnalysisPersistenceNotEnabled`;
the function neither opens connections nor reads configuration and is not called by the current
pipeline or HTTP API.
It is not a Supabase REST endpoint. Once the database owner prepares the table, this boundary
can be implemented using the backend's existing SQLAlchemy connection pattern.

The repository now includes schema-only PostgreSQL models and migration `7d2c91a4e8b6`
(after the résumé migration `02a858fed0df`): one `job_postings_analyses` parent and five
ordered detail tables. The parent has 25 columns, including backend-only `is_open`
(default `true`, temporarily treating all jobs as open); the Agent still returns exactly
28 fields. Seven analysis-management columns are intentionally omitted. See [JPA storage schema](../docs/decisions/JPA-STORAGE-SCHEMA.md)
for field mapping, constraints, query examples and offline verification. This does **not**
activate PostgreSQL result saving: the API/worker still uses local SQLite and JSON, and the
reserved save function still refuses remote writes. Only the database owner applies the
migration after review and merge; no migration or backfill runs at application startup.

### Analyze one posting through HTTP

`POST /job-postings/{id}/analyze` requires `X-Job-Analysis-Token` matching the server token.
It waits for analysis and returns `job_posting_id`, `status`, `structured_data`, `error_message`.
The inner `structured_data` is the frozen contract in `app/schemas/job_posting_analysis_v13.json`.
Use a client timeout that accommodates the Agent timeout.

- No body or `{}` reuses existing local results. `{"force": true}` explicitly retries finished work.
- Success or a saved analysis failure returns HTTP `200`; inspect `status`, not HTTP code alone.
- A job already running returns `202` without another Agent call; force does not take it over.
- Unknown source IDs return `404`, invalid requests `422`, lost ownership `409`, and source/local
  storage failures safe `503` messages. A blank server token disables the endpoint.

### First backfill and new-posting discovery

From `backend/`, enqueue source IDs without making Agent calls:

```bash
python -m scripts.job_posting_analysis_worker --enqueue-only --limit 10
```

`--enqueue-only` does not require an Azure endpoint and never processes queued jobs.
`--batch-size` (default 500) and `--limit` apply only to this mode; it cannot be combined
with `--once`. The limit counts new queue entries. Discovery uses ID keyset pages and preserves every
existing local state, including failed entries. It does not rely on ingestion timestamps.
The default scope includes all stored postings; existing IDs whose content changes are not
automatically reanalyzed.

Run the worker to analyze queued postings and discover new IDs:

```bash
python -m scripts.job_posting_analysis_worker --once
python -m scripts.job_posting_analysis_worker --scan-seconds 60
```

Startup recovers expired work and scans source IDs. `--once` still performs that scan, then
processes at most one posting; it does not limit discovery to one source row. Continuous mode
rescans between jobs every 60 seconds by default, so long model calls can delay scans. Ordinary
failed analyses do not automatically retry or block other jobs. No scheduler or service is installed.

### Interrupted task recovery

Each running attempt has a unique token and a 120-second lease, renewed by a background
heartbeat every 40 seconds. Ctrl+C/`SystemExit` requeues its owned attempt when cleanup can run.
After an abrupt exit, the next worker startup/scan or POST for the same ID recovers an expired
attempt. Valid live leases are preserved, and expired or superseded attempts cannot renew or
save late results.

Recovery restores the export from the last committed SQLite result, or removes an uncommitted
first export, before requeuing. Filesystem errors leave recovery pending. A continuous worker
that loses ownership waits and rescans; `--once` returns failure. Other storage errors stop it.
A model response cannot be resumed midway: recovery repeats the whole JD analysis and may
incur another Azure charge if the earlier request completed remotely.

Use local storage on one machine with a correct clock. Stop older local workers/API processes
before switching versions. Normal v13 configuration opens its own queue under `/v13`; it does
not open or migrate the old v10 queue. SQLite queue initialization is local and is not a
Supabase migration.

### Output validation and evaluation limits

Before a new result is saved, local checks enforce:

- Strict JSON, the v13 schema, direct posting identity, nonblank values and correct null
  handling. Only the six complex fields require evidence; `benefits` must be a string or `null`.
- Exact contiguous evidence excerpts from actual decoded source fields; numeric/boolean
  evidence must match its complete JSON scalar representation. No quote rewriting occurs.
- Exact direct copies for the 13 copied metadata fields, without evidence wrappers; qualification
  categories must be nonempty and unique.
- Nonnegative monetary bounds in the correct order, nonblank optional compensation strings,
  and consistency between populated salary summaries and reported base-pay arrangements.
  Unknown summaries remain allowed; currency/period/amounts are not guessed or repaired.

A rejected response becomes a local failed record with bounded rule codes and field paths.
It is not exported as new structured data and cannot replace a previous successful result.
Cached results and older exports are not retroactively revalidated. The Agent adapter receives
a separate copy of the original source snapshot, so input mutation cannot bypass quote checks.

These rules verify structure and provenance. They cannot prove that a paraphrase, requirement
level, AND/OR logic, workplace classification, salary amount/period or completeness is correct.
Direct fields without evidence are still required to be input-supported by the Agent contract;
local validation does not prove their semantic support.
Separate sample review remains necessary. Earlier v10 live acceptance results do not validate
the new v13 format. The offline suite uses simulated Agent responses; any real v13 acceptance
request is a separate, explicit step. Real input/output files stay in ignored local exports.

Formal tests under `tests/` use synthetic inputs, fake Agents and temporary local databases.
Personal scripts, virtual environments, historical future-table drafts and acceptance artifacts
remain ignored local files; the unrelated existing resume tests are unchanged.

## Users and résumé tables

- `users.id` is the student's Supabase Auth id (`auth.users.id`). Supabase keeps the password; the
  `users` row holds the onboarding answers and is created when onboarding is confirmed.
- Only résumés the student confirmed ("Looks right") are stored. Unverified Agent output and the
  extracted text are never saved.
- `resumes.confirmed_data` keeps all 13 sections as confirmed and is the source of truth. The child
  tables (`resume_experiences`, `resume_educations`, `resume_projects`, `resume_achievements`,
  `resume_skills`) hold the parts the agents query and are rebuilt from it whenever a résumé is edited.
- A student keeps every version; `users.active_resume_id` points to the one the agents use.
- The `users.id → auth.users` foreign key exists only in the migration; `migrations/env.py` stops
  autogenerate from proposing to drop it.

## Changing the schema

1. Edit or add a model in `app/models/` (and import new models in `app/models/__init__.py`).
2. Generate a migration:
   ```bash
   alembic revision --autogenerate -m "describe the change"
   ```
3. **Review the generated file.** Autogenerate treats a rename as drop + add (data loss) and ignores RLS, triggers and functions; add those by hand.
4. Preview the SQL without touching the database: `alembic upgrade head --sql`
5. Open a PR. The migration is reviewed like any other code.
6. **After the PR is merged into `dev`**, the database owner (currently Abanish) runs `alembic upgrade head` from an up-to-date `dev`, then `alembic current` to confirm. Nobody else applies migrations to the shared database.

## Shared database rules

1. **Schema changes only go through Alembic.** Never create or alter tables in the Supabase dashboard. Viewing and editing rows there is fine.
2. **Never edit a migration that has been applied.** Write a new one.
3. **Only the database owner (currently Abanish) applies migrations**, from `dev`, after the PR is merged. Never run `alembic upgrade head` on the shared database yourself, not even from a feature branch to test; ask the database owner instead. The owner announces it in the team chat when it's done.
4. **No `alembic downgrade` on the shared database** except by the database owner, after telling the team. It can drop tables and their data.
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
