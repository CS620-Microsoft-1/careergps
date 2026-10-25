# Local Skill Gap web preview

This change connects the reviewed resume to the existing CareerGPS pages.

## Included

- Confirming Review opens Dashboard and starts one Skill Gap analysis. The green
  banner shows progress; navigation and refresh reuse the saved run.
- Dashboard displays the market sample, resume evidence breakdown and priority gaps.
- Career Analysis displays required, preferred-only and unspecified demand for
  Software Engineer, Data Analyst and AI Engineer from backend local JSON.
- Skill Gaps displays evidence strength, gap grades and original quotations.
- Profile and the account menu use confirmed resume information. Unscored skills
  stay separate from missing evidence.

The Agent extracts evidence; Python calculates the gaps. No database is used.
Reviewed information stays in the current browser tab; analysis files are saved
under `backend/local_results/web_skill_gaps/` and are not committed.

## Configure

Install the existing backend requirements in `backend/.venv` and frontend
dependencies with `npm ci` in `frontend/`. For real analysis, sign in with
`az login` and create an ignored `backend/.env` containing:

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_AGENT_NAME=<resume-agent>
SKILL_GAP_FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
SKILL_GAP_FOUNDRY_AGENT_NAME=<skill-gap-agent>
```

The saved Skill Gap Agent must match the checked-in
[Instructions](../../backend/app/prompts/skill_gaps/Instructions.md) and
[response Schema](../../backend/local_experiments/skill_gap_core_v12/response-format.json).
Synchronize both sides and restart the backend after changing Instructions.
`DATABASE_URL` is not required for this local preview.

## Run locally (Windows PowerShell)

Terminal 1, from `backend/`:

```powershell
$env:LOCAL_CORS_ORIGINS="http://localhost:3100,http://127.0.0.1:3100"
.\.venv\Scripts\python.exe -m uvicorn app.local_main:app --host 127.0.0.1 --port 8011
```

Terminal 2, from `frontend/`:

```powershell
$env:NEXT_PUBLIC_LOCAL_MODE="true"
$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:8011"
$env:CAREERGPS_LOCAL_PREVIEW="1"
node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3100
```

Open http://localhost:3100/onboarding, upload a resume, review the extracted fields
and select **Confirm and open dashboard**. Use the same tab to access Dashboard,
Career Analysis, Skill Gaps and Profile. Existing matching results are reused;
**Analyze again** explicitly starts a new run.

Overall career readiness, common responsibilities and action plans remain
unavailable. Evidence scores describe the resume, not ability or hiring probability.
