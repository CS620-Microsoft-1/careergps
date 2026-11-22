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

## Tests

| Command | What it runs |
| --- | --- |
| `npm test` | Unit tests for `lib/` (Node test runner) |
| `npm run test:components` | Component tests (Vitest and Testing Library); `npm run test:components:watch` reruns on save |
| `npm run test:e2e` | End-to-end tests (Playwright); `npm run test:e2e:ui` opens the Playwright UI |

`npm test` needs Node 22.18 or newer (it runs `.mts` files with Node's built-in type stripping);
on an older Node 22, run `NODE_OPTIONS=--experimental-strip-types npm test`.

Pull requests to `dev` that touch `frontend/` run all of these, plus lint, typecheck and build
(`.github/workflows/frontend-tests.yml`).

## End-to-end tests

Playwright drives the real pages in a headless browser. The API is mocked by
`e2e/support/mock-api.ts` through `page.route()`, so the tests need no backend and no Agent call.
Login is real: `playwright.config.ts` reads the Supabase settings from `.env.e2e`, `.env.local` or
`.env`, builds the app and starts it on port 3000. A server already on port 3000 (`npm run dev`)
is reused on your machine.

- `e2e/public.spec.ts` covers the signed-out pages and needs no account.
- `e2e/signed-in/` starts from a session that `e2e/auth.setup.ts` saves by logging in once. Set
  `E2E_EMAIL` and `E2E_PASSWORD` to a Supabase test account with a confirmed email (see
  `.env.example`); without them these tests are skipped. Never use a real student's account.
  - `route.spec.ts`: Home, Gaps, saving a resource to the plan, the gap filter, Destinations.
  - `resources-taken.spec.ts`: marking a UW course taken on Resources (Undo is off until the
    course is saved), "Not now" on a résumé suggestion, and showing taken courses again.
  - `gaps-taken.spec.ts`: the "You took …" reminder on a Gaps card.

`mockApi(page, options)` answers from `test/fixtures.ts`. Options change what one test sees:
`planItems`, `resources` (the taken-course specs pass `e2e/support/uw-courses.ts`, which adds
three UW–Madison courses), `takenCourses` and `resumeCourseMatches`. It returns the recorded
`calls`, the `taken` course ids, and `holdCourseSaves()` to keep a course save unanswered.

```bash
npx playwright install chromium   # once; downloads the browser (about 100 MB)
npm run test:e2e                  # builds and starts the app, or reuses a server on port 3000
npx playwright test --headed      # watch it run
npx playwright show-report        # after a failure
```

## Structure

```text
app/                 routes, layouts, global styles
components/ui/       shadcn/ui primitives (owned source, restyle freely)
components/layout/   app shell: sidebar, topbar, mobile nav, user menu, page header, backend status
components/auth/     login, signup, onboarding pieces
components/plan/     action plan page, saved-plan state, suggested plan
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

**Planned, not built yet.** The **Ask CareerGPS** panel will be the single place for questions,
explanations and sources, with each answer carrying its citations and the agent steps behind it.
Until it exists, an agent's one-line reason is shown inline on its card (resource picks on Resources,
steps of a suggested plan on Action plan). Don't add separate "why", source or analysis-detail panels.

## Suggested action plan

On `/plan`, **Suggest a plan** (or "or let us suggest a plan" on an empty plan) opens
`components/plan/suggested-plan.tsx`, which calls `streamActionPlanSuggestions` (`lib/api/action-plans.ts`,
backend `POST /action-plans/suggestions/stream`). A first plan can take up to a minute, so
`components/plan/plan-building.tsx` shows the real build stages as they stream in: the gaps read, the
shortlist counts, the mentor choosing (cycling through real shortlisted titles), then the check. There's
no progress percentage, only elapsed time. A repeat is cached and comes back at once. Each card has its
own **Add to plan**.
**Add all to my plan** saves each step with `position` 1..N (clubs without one) through
`PUT /plan/items/{id}`. `orderPlan` (`lib/career.ts`) puts steps with a position first, in that order,
then the rest by gap; resources saved one by one still slot in by gap.
