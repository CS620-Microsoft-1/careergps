# Three fictional reviewed résumés

These inputs use the existing `ReviewedResume` wrapper: `confirmed: true` plus the current `ResumeClassification` object. They contain no evidence scores or market statistics. All names, organizations, projects, and experiences are invented.

| Case | Fictional candidate | Evidence profile |
|---|---|---|
| `01_foundational_student` | Jamie Example | One basic Python project; SQL coursework; JavaScript and Git workshop/list mentions |
| `02_frontend_developer` | Morgan Example | Applied Git collaboration; JavaScript and React project/testing evidence; Python and SQL coursework |
| `03_backend_developer` | Riley Example | Python, PostgreSQL, SQL, and Docker project/testing evidence; applied Git collaboration; JavaScript listed only |

All cases are compared with the same `job_descriptions.json` and `target_scope.json` in the parent directory. That scope mixes frontend, backend, platform and full-stack entry-level Software Engineer roles; it is not a dedicated frontend/backend suitability evaluation.

From the backend directory, run:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_skill_gap_cases
```

This makes actual Azure Agent calls and saves an organized bundle under `backend/local_results/skill_gap/resume_cases/`. The default is sequential execution, with bounded retry/backoff on Azure rate limits. It does not use a database or upload code.

To continue a failed bundle without repeating completed cases:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_skill_gap_cases --resume-bundle PATH_TO_EXISTING_BUNDLE
```

When resuming the same batch, completed intermediate responses can be reused only when the prompt and full request match; the pipeline validates them again. Failed attempts remain available. Start a new bundle if remote Agent Instructions have changed and fresh results are required.
