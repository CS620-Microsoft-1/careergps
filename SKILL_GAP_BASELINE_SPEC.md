# SPEC: Skill Gap baseline latency test (single Agent)

> **Status:** Draft, not started · **Branch:** `test/skill-gap-latency-experiments` (from `dev` @ `77d5ad8`)
> **Owner:** Abanish · **Last updated:** 2026-11-03
> Temporary file in the repo root, used to continue on another device. Later it moves to
> `docs/experiments/SKILL_GAP_LATENCY_PLAN.md`.

---

## 1. Why we are doing this

A Skill Gap run takes **60–80 s**, and students watch a progress screen the whole time. Before changing the
pipeline, we want **measured numbers**: first a clean **baseline** of today's setup, then a comparison with faster
options.

This spec covers **only the baseline (config A)**: today's single Foundry Agent, unchanged.

### What we already know (from 2 local runs, `backend/local_results/web_skill_gaps/`)

| Run | Total | Model call | Input tokens | Output tokens | of which reasoning |
|---|---|---|---|---|---|
| Software Engineer (22 skills) | 81.0 s | 79.0 s | 11,429 (6,400 cached) | 8,779 | 6,016 |
| Data Analyst (18 skills) | 64.0 s | 60.6 s | 10,890 | 6,602 | 5,184 |

- About **97% of the time is the single model call**. Auth, preparation and Python scoring take about 2 s together.
- The model writes about **120 tokens per second**. Time follows **output** tokens. Reading the input takes about 6 s.
- About **70% of the output is hidden reasoning** (Agent setting `reasoning.effort = "medium"`, model **gpt-5-mini**).
- Input share: core skills list about 34%, résumé about 30%, response schema about 26%, instructions about 10%.
- The résumé is sent and read **once**. The slow part is the model judging each of the ~22 skills in its reasoning.

### Overall experiment (for context; only A is in scope now)

| | 1 call | 3 parallel calls (one per skill group) |
|---|---|---|
| **medium effort** | **A: baseline (this spec)** | C |
| **low effort** | B (next) | D |

- **B** needs a way to set `low` effort: a per-request override (unverified with a pinned Agent version), a second Agent
  version, or a direct gpt-5-mini call. Decide when we get to B.
- **C/D**: a teammate has 3 sub-agents in his Azure. Waiting on the endpoint and agent names (**never share keys in chat**).
- Ruled out: embeddings/RAG for the résumé. It only shrinks the ~6 s input part and risks missing evidence.
- Already true: the analysis **starts right after the résumé is confirmed** (`frontend/components/setup/setup-flow.tsx`
  → `queueSkillGapAnalysis` → `/onboarding/route` auto-starts the run). Starting earlier would break the
  "only confirmed résumé data" rule.

---

## 2. How the current pipeline works (code pointers)

```
POST /skill-gaps/runs                         backend/app/api/routes/skill_gaps.py
  └─ SkillGapRunManager.submit()              backend/app/services/skill_gaps/runs.py   (1 worker; cache by résumé+role)
       └─ _work()
            ├─ prepare(family, résumé, id, catalog)   services/skill_gaps/input.py   → payload
            ├─ invoke(payload, save, on_request, timings)   services/skill_gaps/transport.py
            │    ├─ checks the Agent's saved Instructions + schema against the local copies (validate_definition)
            │    └─ ONE responses.create(agent_reference = pinned version, max_output_tokens=40000)
            └─ calculate_web_report(family, output, catalog, market, sources)   services/skill_gaps/response.py
```

- Instructions: `backend/app/prompts/skill_gaps/Instructions.md`. Schema: `build_schema()` in `services/skill_gaps/schema.py`.
  Assets: `services/skill_gaps/data/` (`core_catalog.json`, `market_snapshot.json`, `response-format.json`).
- Settings: `SkillGapSettings` in `backend/app/core/config.py` (`SKILL_GAP_FOUNDRY_PROJECT_ENDPOINT`,
  `SKILL_GAP_FOUNDRY_AGENT_NAME` in `backend/.env`). **Never print `.env`.**
- Offline re-scoring of a saved response: `backend/scripts/replay_skill_gap_response.py`.
- Skills per role: SWE 22 (7 modules), DA 18 (6), AI 23 (7).
- Known issue (fix later, not here): the run cache `fingerprint` in `runs.py` doesn't include the model or reasoning effort.

---

## 3. Baseline test design

**3 roles × 3 synthetic résumés × 3 repeats = 27 runs**, all through today's Agent, unchanged.

### 3.1 Test résumés (9, synthetic)

| | Strong | Medium | Weak |
|---|---|---|---|
| Software Engineer | SWE-1 | SWE-2 | SWE-3 |
| Data Analyst | DA-1 | DA-2 | DA-3 |
| AI Engineer | AI-1 | AI-2 | AI-3 |

- **Strong:** internships plus 3–4 detailed projects with methods, checks and results (most choices; slowest).
- **Medium:** 1 job or internship, 2 projects, some coursework (typical student).
- **Weak:** mostly coursework and one class project (many `knowledge`/`absent` verdicts; fastest).
- **Format:** confirmed résumé JSON in the `ResumeClassification` shape (`backend/app/schemas/resume.py`),
  the same as `resumes.confirmed_data`. **No PDFs**: parsing calls a different agent and would mix its time in.
- Each file must pass `ResumeClassification.model_validate`. Realistic UW–Madison students, clearly fake names and
  contact details. Claude drafts them, Abanish reviews them.
- **Never commit a real résumé.** The 2 existing local runs used Abanish's own résumé. It's fine as a local-only extra, never in git.

### 3.2 Run rules

| Rule | Why |
|---|---|
| Script calls `prepare()` + `transport.invoke()` directly, not the API/UI | The app's cache would return repeats 2–3 instantly |
| One run at a time | Parallel runs share quota and distort timing |
| Interleave: round 1 = all 9, then round 2, then round 3 | Spreads Azure slowdowns across all résumés |
| Same Agent version for all 27; record it | Comparable runs |
| No retries; a failed run is recorded as failed | Same as production |

Expected duration: about **30–40 min**. Expected cost: about **$0.50–0.60** (approximate, gpt-5-mini, team quota).

### 3.3 Recorded per run

Saved to `backend/local_results/experiments/skill_gap_baseline/<timestamp>_<resume>_r<round>/` (gitignored):
`input.json`, `agent.raw.json`, `agent.response.json`, `skill_gaps.json` (report), `metrics.json`.

`metrics.json` holds:
- `resume`, `job_family`, `round`, `agent_version`, `started_at`
- `total_seconds`, `inference_seconds`, the other `timings`
- `input_tokens`, `cached_tokens`, `output_tokens`, `reasoning_tokens`
- `status`, `error`
- the verdict and chosen `operation_id` per skill, `reference_errors`

### 3.4 Summary output (`results.md`)

Per résumé and per role:
- mean, fastest and slowest time
- mean tokens, by type
- **agreement across the 3 repeats** (same verdict, same activity): the **noise floor**
- invalid quotes
- failures

---

## 4. Work plan (in order)

1. **Résumés:** write `backend/experiments/skill_gap_baseline/fixtures/{swe,da,ai}_{strong,medium,weak}.json`. Abanish reviews them.
2. **Runner:** `backend/experiments/skill_gap_baseline/run.py`, for example
   `python -m experiments.skill_gap_baseline.run --repeats 3` (also `--resume swe_strong`, `--dry-run`, `--max-calls N`).
   It reuses `prepare`, `invoke`, `calculate_web_report`, `load`, `ASSET_ROOT`. App code stays unchanged.
3. **Summary:** `backend/experiments/skill_gap_baseline/summarize.py` → `results.md`.
4. **Unit tests** (no network, run in CI): `backend/tests/test_skill_gap_baseline_experiment.py`
   - the fixtures validate
   - the runner with a mocked `invoke` writes the expected files and `metrics.json`
   - interleaved order
   - the summary math (mean, min/max, agreement)
5. **Smoke run:** 1 real call on `swe_strong` to check the setup, the Agent version and the recorded fields.
6. **Baseline:** all 27 runs. Share `results.md` with the team.
7. Move this spec to `docs/experiments/`, add the results, open a PR into `dev`.

## 5. Checklist on a new device

- `git fetch && git switch test/skill-gap-latency-experiments`
- `cd backend && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Create `backend/.env` with the Skill Gap Foundry endpoint and agent name (copy them securely, never via git or chat).
- `az login` (Azure CLI) with an account that has a Foundry role on the project.
- `python -m unittest discover -s tests` passes.

## 6. Team conventions to keep

- Commits use Conventional Commits with a scope (`test(backend): ...`, `docs(experiments): ...`). **No `Co-Authored-By` lines.**
- PRs go into `dev`, with a brief description ending in a note that tags the team (only one reviewer can be selected on the free plan).
- Ask before pushing or opening PRs. Explain each step and wait for approval before implementing it.

## 7. Open questions

- Résumé levels and counts OK as above (3 × 3 × 3)?
- Gold labels (correct verdicts for ~10 skills on 2 résumés): needed for the A vs B quality check. Label them **before** seeing results.
- For B: how to set `low` effort (override, second Agent version, or a direct model call).
- Teammate's 3 sub-agents: endpoint, agent names, model and effort, their instructions and schema, and our access and quota.
