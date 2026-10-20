# Three complex fictional reviewed résumés

All content is invented and follows the existing Review-page JSON schema. No evidence scores or demand ratios are prefilled. The cases include multiple education, work, research and project entries, with publications, awards, certificates and leadership activities.

| Case | Candidate | Main test coverage |
|---|---|---|
| `01_backend_data` | Avery Example | Python/SQL validation across distinct entries; PostgreSQL and Docker project evidence; JavaScript coursework; no React project |
| `02_frontend_fullstack` | Taylor Example | React/JavaScript validation across work and projects; applied Python/SQL; PostgreSQL listed only; Docker absent |
| `03_systems_research` | Casey Example | Systems skills and publications; Python validation across research/projects; SQL work with SQLite, not PostgreSQL; Docker applied without explicit validation |

These cases test the existing scoring rules, including the current rule awarding 1.00 for validation in two eligible entries. They do not fix or validate that rule's calibration. A negative statement about a technology is not positive evidence of skill; inspect the original Agent citations for such edge cases.

Run from the backend directory:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_skill_gap_cases --case-set complex
```

Execution is sequential by default, uses actual Azure Agent calls with bounded rate-limit retries, and does not use a database. The shared synthetic job-description input is the same as the earlier basic résumé batch, so changes in evidence scores can be compared without switching the job sample. Market extraction can be reused within the same batch only when its request and local prompt match exactly.

Each new bundle is saved under `backend/local_results/skill_gap/complex_resume_cases/`. The bundle and every successful case contain a copy of the job descriptions, the reviewed résumé, readable résumé, original Agent response JSON, calculated result and report. Detailed provenance is retained under `runs/`.
