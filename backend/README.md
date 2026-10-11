# CareerGPS Backend

Python 3.12+ · FastAPI · SQLAlchemy · Alembic · PostgreSQL (hosted on Supabase). See [ADR-002](../docs/decisions/ADR-002-CareerGPS-Backend.md).

The whole team shares **one Supabase Postgres database**. There is no local database to set up.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
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

## Project layout

```text
app/
├── main.py                  # FastAPI app: CORS + routers (entry point for uvicorn)
├── core/
│   ├── config.py            # Settings read from .env (DATABASE_URL, CORS_ORIGINS, SUPABASE_URL)
│   ├── options.py           # sign-up choices (target roles, experience levels); mirrors the frontend
│   └── security.py          # verifies Supabase Auth access tokens (JWTs)
├── api/
│   ├── deps.py              # get_db, get_current_user (token), get_current_db_user (token + users row)
│   └── routes/
│       ├── health.py        # GET /health, GET /health/db
│       ├── me.py            # POST /me, GET /me, PATCH /me/profile
│       └── resumes.py       # upload, poll, retry, confirm
├── db/
│   ├── base.py              # SQLAlchemy Base; every model inherits from it
│   ├── session.py           # engine + SessionLocal, built from settings
│   └── check_connection.py  # connectivity test
├── models/
│   ├── __init__.py          # import every model here so Alembic can see it
│   ├── user.py              # id = Supabase Auth account id
│   ├── profile.py
│   ├── resume.py            # one uploaded PDF + parsing status
│   └── resume_data.py       # educations, experiences, skills, projects (written on confirm)
├── schemas/                 # Pydantic request/response models
└── services/                # business logic, called by the routes
    ├── pdf.py               # PDF checks + pdfplumber text/link extraction
    ├── storage.py           # Supabase Storage (private bucket)
    ├── llm.py               # Azure OpenAI; the only module that knows the provider (ADR-003)
    └── parsing.py           # background job: PDF → text → LLM → parsed_data
migrations/
├── env.py                   # Alembic setup: reads settings, loads models
└── versions/                # migration files (committed, never edited once applied)
tests/                       # unittest; run by CI on every PR to dev, no DB needed
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
| `POST /resumes` | Upload a PDF (multipart `file`, ≤ 10 MB, ≤ 10 pages). **202**; parsing runs in the background. **409** if the user already has a résumé that isn't `failed` |
| `GET /resumes/{id}` | Status (`pending` → `parsing` → `parsed` / `failed` → `confirmed`), `error_code`, `parsed_data`. Poll this |
| `POST /resumes/{id}/retry` | Parse a `failed` résumé again |
| `POST /resumes/{id}/confirm` | Save the user-checked data to the structured tables. Only from `parsed` |
| `/docs` | Interactive API docs (Swagger UI), generated from the code |
| `/openapi.json` | The API contract; the source of truth for frontend types (ADR-002) |

### Authentication

Sign-up, login and logout happen in the frontend with Supabase Auth; the API never sees passwords.
The frontend sends the Supabase access token as `Authorization: Bearer <token>`. The API checks its
signature (Supabase's public signing keys, or `SUPABASE_JWT_SECRET` on legacy projects), expiry,
audience and issuer. Missing or invalid token → **401**.

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

## Changing the schema

1. Edit or add a model in `app/models/` (and import new models in `app/models/__init__.py`).
2. Generate a migration:
   ```bash
   alembic revision --autogenerate -m "describe the change"
   ```
3. **Review the generated file.** Autogenerate treats a rename as drop + add (data loss) and ignores RLS, triggers and functions; add those by hand.
4. Preview the SQL without touching the database: `alembic upgrade head --sql`
5. Open a PR. The migration is reviewed like any other code.
6. **After merge**, the migration owner runs `alembic upgrade head` from `main`.

## Shared database rules

1. **Schema changes only go through Alembic.** Never create or alter tables in the Supabase dashboard. Viewing and editing rows there is fine.
2. **Never edit a migration that has been applied.** Write a new one.
3. **Only apply migrations from `main`, after merge, by one person.** Announce it in the team chat.
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
