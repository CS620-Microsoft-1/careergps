# CareerGPS Frontend

Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui, per [ADR-001](../docs/decisions/ADR-001-CareerGPS-Frontend.md).

## Run locally

Requires Node.js 20.9 or newer (the minimum for Next.js 16).

### Windows

Install [Node.js 20 or newer](https://nodejs.org/en/download), open a new PowerShell window, and
verify the installation:

```powershell
node --version
npm --version
```

### macOS

With Homebrew, install the current supported Node.js release. The project accepts Node.js 20.9 or
newer:

```bash
brew install node
node --version
npm --version
```

```bash
cd frontend
npm ci
cp .env.example .env.local   # then set NEXT_PUBLIC_API_URL if the API isn't on port 8000
npm run dev
```

Use `npm install` instead of `npm ci` only when intentionally changing dependencies or updating
`package-lock.json`.

Open http://localhost:3000. Start the backend too (see `backend/README.md`) so the app can
reach the API.

During the current test phase, onboarding uploads the selected PDF or DOCX to the transient
`POST /resumes/analyze` endpoint and shows the extracted text plus an editable Agent
classification. Choosing **Looks right, continue** discards the in-memory result and navigates
to the existing placeholder dashboard. Refreshing during Review also discards the result.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Start the dev server |
| `npm run build` | Production build (also type-checks) |
| `npm run lint` | Run ESLint |
| `npm run typecheck` | Generate route types and run the TypeScript compiler |

## Structure

```text
app/                 routes, layouts, global styles
components/ui/       shadcn/ui primitives (owned source, restyle freely)
components/layout/   app shell: sidebar, topbar, mobile nav, user menu, page header, backend status
components/auth/     login, signup, onboarding pieces
components/panels/   Copilot panel and the hook to open it from anywhere
components/common/   shared building blocks (logo, form fields, empty states)
lib/                 nav items, form options, validation schemas, utilities
lib/api/             every call to the backend API (see "Connect to the backend")
types/               shared TypeScript types (types/api.ts: API response shapes)
```

Add more shadcn components with `npx shadcn@latest add <name>`.

## Connect to the backend

The app calls the FastAPI backend at `NEXT_PUBLIC_API_URL`, set in `.env.local` (copied from
`.env.example`; defaults to `http://localhost:8000`).

- **Restart `npm run dev` after changing `.env.local`.** `NEXT_PUBLIC_` values are built into
  the browser code when the dev server starts.
- **Never put secrets in a `NEXT_PUBLIC_` variable.** Anyone can read them in the browser.
- The backend only accepts browser calls from origins listed in `CORS_ORIGINS` in
  `backend/.env` (default `http://localhost:3000`). Running the frontend on another port means
  adding it there.

## Sign-up and login

Accounts live in Supabase Auth (SPEC-001). Set `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in `.env.local` (ask the team for the publishable key).

- `/signup` asks only for email, password and the terms checkbox, calls `supabase.auth.signUp`
  (the terms consent goes in user metadata), then shows
  "Check your email". The link in that email lands on `/auth/confirm` (or on `/`, which passes the
  code on), which creates the session and calls `POST /me`.
- `/login` calls `signInWithPassword`, then `POST /me` too if sign-up wasn't finished yet.
- `proxy.ts` refreshes the session cookies and redirects: logged out → `/login` for app pages,
  logged in → `/dashboard` from `/login` and `/signup`. The API checks the token again on every call.
- `lib/supabase/client.ts` registers the access token with `lib/api/client.ts`, so every API call
  sends `Authorization: Bearer <token>`.
- Supabase's built-in mailer sends 2 emails an hour, only to members of the Supabase organization.
  For testing, create confirmed users in Supabase → Authentication → Users instead.

The **backend status badge** (bottom of the sidebar, and in the account menu on small screens)
shows whether the app can reach the API and database. Hover it for details.

| Badge | Meaning | Fix |
| --- | --- | --- |
| 🟢 Backend connected | API and database both reachable | — |
| 🟠 Database unreachable | API is up, database isn't | Check `DATABASE_URL` in `backend/.env`; resume the Supabase project if it paused |
| 🔴 Backend unreachable | No answer from the API | Start it (`uvicorn app.main:app --reload`); check `NEXT_PUBLIC_API_URL` and `CORS_ORIGINS` |

### Calling the API

All backend calls go through `lib/api/`. Components never call `fetch()` directly.

```text
lib/api/client.ts    shared plumbing: base URL, timeout, errors (ApiError)
lib/api/health.ts    one file per backend router, same name: backend/app/api/routes/health.py
```

To add a call, put a small function in the matching file (create it if the router is new) and
type the response in `types/api.ts`:

```ts
// lib/api/health.ts
export function getDatabaseHealth() {
  return apiGet<DatabaseHealthResponse>("/health/db");
}
```

`ApiError.status` is the HTTP status (e.g. `503`), or `0` when no response arrived at all (API
down, timeout, or blocked by CORS). Response types are hand-written for now and will be
generated from the API's `/openapi.json` later.

## Responsive rules

Every screen must work from a 320px phone to a 2560px monitor, and must respect the
browser's font-size setting. Follow these rules when building pages:

1. **Sizes in rem, not px.** Use Tailwind's scale (`h-10.5`, `max-w-100`) and the type
   tokens in `app/globals.css` (`text-control`, `text-title`, `text-page-title`,
   `text-display`). Raw `px` is only for borders, rings and hairlines.
2. **Mobile first.** Write the phone layout unprefixed, then add `sm:` (640px), `md:` (768px),
   `lg:` (1024px), `xl:` (1280px). Breakpoints are rem-based, so they also follow browser zoom.
3. **Center bounded content.** Page content uses `mx-auto w-full max-w-290` so wide
   screens stay balanced instead of hugging the left edge.
4. **Use `dvh`, not `vh`, for full-height layouts** (`min-h-dvh`), so mobile browser
   toolbars don't cut content off. Tall content scrolls inside its own column on short screens.
5. **Grids and flex shrink safely.** Use `grid-cols-[minmax(0,1fr)…]` / `min-w-0` on flex
   children, and let rows wrap. Only tables and code blocks may scroll sideways, inside
   their own `overflow-x-auto` wrapper.
6. **Respect notches.** Fixed elements near screen edges (e.g. the Ask CareerGPS button) add
   `env(safe-area-inset-*)` to their offset.
7. **Touch targets** are at least 36px (buttons) / 42px (inputs) tall.

Check each new screen at 320, 390, 768, 1024, 1366×650 (short laptop), 1920 and 2560 wide,
plus with the browser's default font size raised to 20px. No page may scroll horizontally.

## Copilot

The **Ask CareerGPS** panel (`components/panels/`) is the single place for questions,
explanations and sources: there are no separate "why", source or analysis-detail panels.
Each answer will carry its citations and the agent steps behind it. Any component can open
it with `useCopilot().openCopilot("Why is Docker a high-priority gap?")`.
The answer format is designed together with the backend Copilot API; until then the
panel is a shell with the input disabled.
