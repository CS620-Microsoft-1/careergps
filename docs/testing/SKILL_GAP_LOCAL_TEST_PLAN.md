# Local Skill Gap experiment

## Latest run — 2026-10-20, structured JD v3

### Follow-up: API-level schema compatibility

- Implemented optional strict per-request schema construction and response-status/token/error metadata; three task schemas remain distinct. The original default mode is preserved, and strict mode never silently downgrades.
- Two fresh strict final-stage replay attempts against the existing configured Azure Agent were rejected. The recorded server response is `400 invalid_payload`, param `text`: "Not allowed when agent is specified."
- The current Agent has therefore **not** passed an API-enforced schema test. The earlier live result remains 2/3 passed; no results were overwritten or labeled as fixed.
- Detail: `backend/local_results/skill_gap/api_schema_replay_20261020T184430Z/response_metadata.json`. New focused suite: 57 tests pass. No DB/cloud-definition/Git mutation occurred.
- Further work needs a choice between configuring distinct Agent-level schemas and using direct model requests. No automatic provider/endpoint substitution was made.

- Added an isolated structured-JD entry point and twenty fictional US software-engineering internships across ten fictional companies (backend/frontend/data/systems/full-stack). Reused the existing three complex reviewed-resume inputs without changing their content.
- All twenty actual Agent JD extractions passed quotation/path, catalog metadata, required/preferred and independent fixture-expectation checks. Alternative examples remained grouped instead of becoming individual mandatory languages.
- Avery/backend and Taylor/frontend completed extraction, Python calculation and final Agent explanation with unchanged numeric fields. Casey/systems passed evidence extraction and calculation, but final JSON remained invalid after three attempts at the larger output budget; its end-to-end status is **failed**, not passed. An earlier smaller-budget response was truncated.
- Preserved rate-limit attempts, rejected responses and corrections in a separate audit folder. Taylor's first response inconsistently marked Linux not evidenced but matched it; the actual Agent corrected this on retry. Concept-only cloud coursework now has a dedicated partial-match regression test and a maximum evidence score of 0.25 without claiming a platform was demonstrated.
- Repeatedly observed incomplete strongest-evidence selection: the Agent omitted explicit Python/SQL/React/Rust testing citations from some corresponding skill criteria, despite recognizing testing separately. Actual scores were not manually inflated. Exact citations and schema checks do not establish semantic completeness.
- All **48** focused unit/regression tests passed. This is separate from the live end-to-end result of **2 passed / 1 failed**.
- Delivery: `backend/local_results/skill_gap/structured_20_20261020/`, with twenty JD JSONs, three resume JSONs, two accepted final Agent JSONs, one rejected final raw `.txt`, and `results.txt` with provisional Casey calculations clearly distinguished from a valid final explanation.
- Audit: sibling `structured_20_20261020_audit/`. Detailed rules and caveats: `docs/testing/SKILL_GAP_STRUCTURED_LOCAL_V3.md`.
- No database connection, migration, remote Agent edit, commit, push or PR. The branch remains `test/skill-gap-agent-local`; inputs/results and `.env` remain git-ignored.

Branch: `test/skill-gap-agent-local`. This experiment runs independently of FastAPI, SQLAlchemy, migrations, and Supabase. No shared database or user table is accessed. Nothing is pushed automatically.

## Pipeline

The current recommended entry is **v2: raw-input extraction**, described next. The original v1 runner remains available for regression tests only.

## V2: Review-page JSON and job descriptions, no prefilled scores

Run from `D:\cs620 proj\backend`:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_skill_gap_local tests.test_skill_gap_extraction -v
.\.venv\Scripts\python.exe -m scripts.test_skill_gap_pipeline
```

The pipeline makes three actual Azure Agent calls, with isolated temporary conversations:

1. Extract each posting's explicitly named skills, `required`/`preferred`/`context`/`negated` labels and exact quotations.
2. Extract each requested résumé skill's evidence category and exact quotation with a JSON pointer to the reviewed field.
3. Explain the scores computed by Python. Every final skill, numerical value and priority is checked against that calculation.

The raw sample files are:

- `backend/tests/fixtures/skill_gap/reviewed_resume.json`: `confirmed` plus the existing `ResumeClassification` contract, representing the edited Review state. It has **no evidence scores**. Personal information is omitted from Agent requests.
- `backend/tests/fixtures/skill_gap/job_descriptions.json`: a wrapper holding company names and existing `NormalizedPosting` objects, including full `description_text`. It has **no counts or frequencies**. Seven fictional records deliberately include one senior vacancy and one duplicate.
- `backend/tests/fixtures/skill_gap/target_scope.json`: target role, seniority, country, date and window. This is configuration, not a market statistic.

The Review page currently keeps its edited classification in frontend state; this experiment exports a matching local wrapper. It does not implement frontend saving or imply that saving to the shared database already exists.

Python filters by explicit role words and seniority markers in the title, known country, and source publication date in the inclusive window ending `as_of`. Generic titles whose seniority is unclear and missing publication/country fields are excluded and logged. This conservative prototype is not a general occupational classifier and must not be described as a representative market sample. It does not infer source publication dates from `first_seen_at`.

Duplicate source IDs or identical company/title/location/description records count once. Conflicting content for one source ID fails instead of silently picking a version. This is exact-record deduplication, not a general semantic duplicate detector.

For each skill:

```text
frequency = unique matched postings / all selected valid postings
matched = required OR preferred (one count per posting)
context and negated mentions = excluded
```

Required and preferred-only counts/frequencies are also saved separately. A skill is never inferred from a parent/related skill: SQL and PostgreSQL are separate. Source quotations must actually contain the named skill or a configured alias. Exact source grounding does not guarantee that the Agent's requirement label is correct; inspect its quotations.

Python maps résumé categories to scores: no evidence = 0; listed = 0.25; applied = 0.60; validated = 0.80. Two validated independent experience/project entries can score 1.00. Repeated quotes do not add up. Applied/validated citations must point to actual `content` fields. These are evidence-coverage heuristics, not verified competence. Missing citations may mean the Agent overlooked evidence; the local audit enables review.

The local Agent instructions are now a three-task prompt in `docs/skill-gap-agent-prompt.md`. Each request includes the prompt, task name, input and exact output JSON schema. The remote Azure Agent configuration is **not edited automatically**; this file can also be pasted into its Instructions field. Original v1 requests without a task still use the explanation task.

Each v2 run saves raw sources, filtering audit, all Agent requests/replies, evidence citations, Python-generated résumé scores and market counts, final JSON, readable report and metadata to a unique git-ignored `backend/local_results/skill_gap/*_pipeline_*/` directory. Invalid extraction halts the pipeline without using fallback scores or accepting a final result. The CLI exits nonzero on failure.

## Legacy v1 pipeline (prefilled fixture scores)

1. Read `backend/tests/fixtures/skill_gap/confirmed_resume.json` (synthetic, manually confirmed skill evidence).
2. Read `backend/tests/fixtures/skill_gap/market_profile.json` (synthetic frequencies, not live job statistics).
3. Normalize known aliases (`JS`, `Postgres`, `React.js`) and match other names case-insensitively. This small dictionary is not a complete skill taxonomy.
4. Calculate `frequency * (1 - evidence_score)`, round to six decimals, and sort descending. Duplicate candidate aliases use the maximum score, not a sum; duplicate market aliases are rejected.
5. Mock mode returns deterministic sample explanations. Live mode sends the prompt and synthetic input to the separately configured Foundry Skill Gap Agent.
6. Validate JSON, skill order, all three numeric fields, priorities, strengths, and sample-confidence flag. Invalid responses are saved as raw text and marked failed, never accepted as valid results.
7. Save inputs, calculated gaps, prompt snapshot, raw reply, validated JSON, readable report, and run metadata in a unique local directory under `backend/local_results/skill_gap/` (git-ignored).

## Run from Windows PowerShell

From `D:\cs620 proj\backend`:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_skill_gap_local -v
.\.venv\Scripts\python.exe -m scripts.test_skill_gap_local --mode mock
.\.venv\Scripts\python.exe -m scripts.test_skill_gap_local --mode live
```

The default is mock. Live mode reads only `SKILL_GAP_FOUNDRY_PROJECT_ENDPOINT` and `SKILL_GAP_FOUNDRY_AGENT_NAME` from `.env`; it does not require `DATABASE_URL`. It uses local Azure identity through DefaultAzureCredential, including an existing `az login`. Access to the new project must already be granted. Live mode makes a real, potentially billable Azure call; local files are the application's result storage, but Azure may retain service logs/responses under its own configuration. The temporary Agent conversation is deleted on a best-effort basis. No remote Agent configuration is modified: the local prompt is included with each request.

You can select different local input files:

```powershell
.\.venv\Scripts\python.exe -m scripts.test_skill_gap_local --mode mock --resume path\confirmed_resume.json --market path\market_profile.json
```

The resume input is a skill-evidence fixture, not the full existing `ResumeClassification` JSON. Automatic evidence extraction/scoring and frontend integration are future work. For this first experiment use synthetic data only.

## Experimental scoring and limitations

- Evidence scores are manually supplied test assumptions: 0 absent evidence; 0.25 skills-list mention; 0.60 project evidence; 0.80 stronger demonstrated evidence. They do not prove actual ability.
- Priority: high >= 0.60; medium >= 0.30 and < 0.60; low < 0.30.
- Sample confidence is low if the input flags it, the sample has fewer than 30 postings, fewer than 3 companies, or no market skills. These are prototype thresholds, not statistically established guarantees.
- No confidence multiplier is applied to the numerical gap. The confidence flag is shown separately.
- Candidate skills with score >= 0.60 may be strengths. Recommendations remain qualitative and require human review.
- Schema/numeric validation cannot prove that every natural-language sentence is correct or free of invented claims; review the report.
- Empty candidate skill lists are valid. Empty market skills return no comparison. Invalid scores, unsupported skills, modified numbers, and wrong priorities fail.

## Verification log

Record run outcomes here when executing this local experiment. This is separate from the shared database/RLS test log because this experiment does not exercise either.

### 2026-10-20 (America/Chicago) — Branch handoff and clean-environment verification

- User requested publication only to `test/skill-gaps`. Fetched current refs and based the work on `origin/test/skill-gaps` at `605590b`, which already matched `origin/dev`. This preserved six upstream commits adding user/resume storage models, migration and documentation without applying any migration or changing another branch.
- Added a separate non-secret `skill-gap.env.example`, a minimal `requirements-skill-gap.txt` with direct versions from the successful environment, and `SKILL_GAP_RUN_LOCAL.md`. The real `.env`, local results, virtual environments and unrelated resume-dataset tools are excluded from the handoff. The template was renamed from `.env.skill-gap.example` after the repository baseline correctly blocked its sensitive-looking filename; the safety rule was not weakened.
- Created a new isolated Python 3.12 environment and installed only the minimal requirements. After installation completed, all **65 focused tests passed**, `pip check` passed, and `--agent-envelope --prepare-only` generated the 20 JD/3 resume inputs successfully without an Agent call or database connection. The first premature test attempt ran while installation was still in progress and failed on missing Azure modules; the completed-install rerun passed unchanged.
- The portability check did not invoke Azure, modify the remote Agent, connect to Supabase, or apply migrations. Existing live findings and limitations above remain unchanged. See the local setup guide for Azure account permissions and the current recommended entry point.
- After staging the renamed template, the existing repository baseline plus the focused Skill Gap suite passed together: **76 tests**. Staged diff whitespace checks also passed. No existing safety check was relaxed.

### 2026-10-20 (America/Chicago) — Agent-configured schema complete rerun

- User configured the unified response schema on the existing Azure Agent and reported increasing deployment quota. No cloud configuration was edited by this local test.
- Earlier attempts were blocked by the 10,000-TPM deployment limit. One completed HTTP response with a 5,000-token output allowance was `incomplete`: all 4,992 output tokens were reasoning and visible JSON was empty. This was not a JSON syntax rejection.
- New fresh run: `backend/local_results/skill_gap/structured_schema_20261020_200k/`, with a separate `_audit` sibling. All 20 JD extractions and all three resumes' evidence/final stages are requested afresh; no prior-run outputs are reused.
- The local envelope runner now allows 25,000 output tokens including reasoning and a 300-second request timeout. Default legacy timeout remains 120 seconds; no per-call reasoning override is sent.
- First two postings returned `completed`; returned format is `json_schema`, named `careergps_pipeline_response`, `strict: true`, and local schema/source validation passed. Remaining stages were still running when this entry was added; this is not yet an all-cases pass.
- All 64 focused unit/regression tests pass. No database, migration, commit, push or PR.

Completed outcome (2026-10-20 19:44 UTC):

- All twenty JD extractions passed citation/catalog validation and exactly matched the independent fixture expectations. All three resumes completed evidence extraction, Python scoring and final explanation; final immutable fields were unchanged.
- Across the initial attempt and its continuation there were **22 actual cloud responses**, all `completed` and all reporting strict `careergps_pipeline_response` JSON Schema. Every returned text parsed as JSON. There were no 429s, refusals or truncated responses in this new campaign.
- The continuation manifest reports 20 live calls, one cached response and five rejected replies. Its cache hit reuses only the first two postings generated earlier in this same campaign, not an old batch. The preserved initial manifest accounts for the other two calls. There were six rejected replies across the campaign: five JD path/source-field errors and one false-positive local negation rejection.
- That false positive quoted a whole paragraph containing positive SQLite experience and a separate denial of PostgreSQL experience. The Agent matched **only SQLite**, correctly. The local broad negation regex rejected the whole paragraph unnecessarily; the actual retry shortened the quote and passed. This must not be reported as the Agent claiming PostgreSQL experience. The guard remains conservative and needs clause-aware refinement.
- Final focused verification: **65 tests pass**. This is a transport/schema/grounding/arithmetic pass, not a semantic-quality pass.
- Human review found persistent underselection of Python/React/Rust test evidence, some questionable Taylor algorithm/data-structure/database classifications, and explanations that confuse programming-language coverage with separate API/frontend requirements. Original Agent JSON and computed values remain unchanged. Detailed review is appended to the run's `results.txt` and the v3 testing document.
- Audit metadata records 652,858 input-plus-output tokens, including 209,728 reasoning tokens, across the 22 responses. Increasing quota avoided this campaign's previous rate-limit obstacle; it did not guarantee low latency or semantic accuracy. The exact configured TPM was not independently read back from Azure management.

### 2026-10-17 (America/Chicago) — First local pipeline test

- Ran the synthetic Mock pipeline successfully. Saved all artifacts in `backend/local_results/skill_gap/20261018T043837Z_mock_1dca6cdf/`. Directory names use UTC; the local run date is October 17.
- Ran the real configured Skill Gap Agent (`olive-agent-nybsd72mqb`) successfully in 28.389 seconds. The first sandboxed attempt could not access Azure CLI's login cache; the permitted retry succeeded with the existing local Azure identity.
- Live artifacts: `backend/local_results/skill_gap/20261018T043848Z_live_6a1cbe4f/`.
- Verified live output against the strict schema, complete skill order, unchanged numeric fields and priorities: Docker 0.8/high, PostgreSQL 0.4875/medium, Git 0.36/medium, JavaScript 0.28/low, Python 0.15/low.
- The pipeline and Agent call did not import or connect to any database. A dedicated subprocess test blocks SQLAlchemy/psycopg imports and verifies no database session module loads.
- Existing regression tests also passed (58 tests at the first run). The repository's pre-existing posting-ingest tests use isolated in-memory SQLite; they did not access Supabase. The Skill Gap pipeline itself uses only JSON files.
- Final focused verification passed all 17 Skill Gap tests, including zero-gap maintenance recommendations, empty market inputs, and sparse-sample confidence. The final changes do not alter the default live sample's scores or prompt.
- No migration, remote Agent edit, commit, push, or PR was performed. Local results and `.env` remain git-ignored.

SDK reference: [Microsoft AIProjectClient documentation](https://learn.microsoft.com/python/api/azure-ai-projects/azure.ai.projects.aiprojectclient) for `allow_preview=True` and `get_openai_client(agent_name=...)`.

### 2026-10-18 (America/Chicago) — Raw-content pipeline v2

- Created synthetic inputs using the existing Review `ResumeClassification` and job-board `NormalizedPosting` contracts. Neither source contains evidence scores, market frequencies, or gap scores.
- The three actual calls to `olive-agent-nybsd72mqb` completed successfully in 64.215 seconds. The local v2 prompt and a per-task JSON schema were supplied on every call; the remote Agent definition was not edited.
- Saved the successful run in `backend/local_results/skill_gap/20261018T052843Z_pipeline_219cc7e3/`.
- Filtered seven records to five eligible, unique entry-level US postings across four fictional companies. Excluded one senior position and one duplicate before computing the denominator.
- Verified exact résumé quotes/paths and job-description quotes. Python mapped evidence categories to scores and counted required/preferred skill mentions. Negated JavaScript/Docker/Kubernetes statements were not counted as requirements.
- Live calculated results: Docker 0.8/high; Git 0.4/medium; PostgreSQL 0.3/medium; SQL 0.3/medium; JavaScript 0.24/low; Python 0.2/low; React 0.08/low. Market confidence was low because the sample has only five postings.
- All 33 focused tests passed, including provenance checks, denominator/deduplication, requirement labels, score mapping, JSON pointers, and unsupported-evidence rejection. No database was used by these tests or the live pipeline.
- All local source/result files remain local; no commit, push, migration or frontend persistence change was performed.

### 2026-10-18 (America/Chicago) — Rerun after user updated Azure Instructions

- User reported updating the remote Agent Instructions. Reran the unchanged raw-content pipeline against the configured Agent with the same reviewed-résumé and job-description fixtures.
- All three actual Agent stages succeeded in 61.415 seconds. Artifacts: `backend/local_results/skill_gap/20261018T053252Z_pipeline_649df8c7/`.
- Source grounding, schema, skill order, all numeric values and final priorities passed validation. Five eligible unique postings across four fictional companies remained after filtering seven source records.
- Evidence scores and all seven gap scores matched the previous run; supporting quotations varied slightly (the new résumé extraction also cited the Python scripting work entry).
- Demand details: Docker 1 required + 3 preferred-only / 5; Git 4 + 1 / 5; JavaScript 2 + 1 / 5; PostgreSQL 2 + 0 / 5; Python 4 + 1 / 5; React 1 + 0 / 5; SQL 1 + 1 / 5. Context/negated Kubernetes mentions contributed zero.
- Interpretation: Docker's combined 80% includes preferred requirements; only 20% explicitly require it. Current ranking weights both equally. Git's medium gap indicates room to document evidence, not lack of Git ability. PostgreSQL and SQL improvements can be demonstrated together in one project.
- Requests still include the local v2 prompt and per-task output schema. This validates the integrated invocation after the reported remote update, not isolated behavior from remote Instructions alone.
- No database, migration, code change, commit or push was used in this rerun. Only local results and this verification log were written.

### 2026-10-18 (America/Chicago) — Three fictional résumé cases

- Added three complete Review-compatible synthetic résumé inputs: foundational student (Jamie Example), frontend developer (Morgan Example), and backend/deployment developer (Riley Example). None contains prefilled evidence scores or market ratios.
- Used the same seven raw posting records and target scope for all cases. Each case selected the same five eligible postings across four fictional companies. Required/preferred counts and computed demand ratios matched across the three successful results.
- All three cases obtained actual Agent responses for job requirements, résumé evidence and final recommendations; all completed the pipeline's grounding, schema and numeric/order validation.
- Bundle: `backend/local_results/skill_gap/resume_cases/20261018T184627Z_b61b0084/`. Each case contains a readable résumé, original Review JSON, three directly accessible Agent response JSON files, final result and report. Detailed runs and failed attempts remain under each case's `runs/` directory.
- The initial parallel attempt encountered Azure rate limits. Continued sequentially with bounded rate-limit backoff and reused already-completed actual responses only where the full request and local prompt matched. Per-run `agent_call_audit.json` records cached sources and new call attempts. Future runs default to one worker.
- The bundle's `comparison.md` and `comparison.json` report all three cases passing and identical market statistics. Cases differ in evidence scores, not their market baseline.
- Foundational student's leading gaps: Docker 0.80, Git 0.75, JavaScript 0.45. Frontend developer's leading gaps: Docker 0.80, Python 0.75, Git/PostgreSQL 0.40. Backend developer's leading gaps: JavaScript 0.45 and Git 0.40; Python/Docker/PostgreSQL/SQL have substantially lower evidence gaps.
- The unified target mixes frontend/backend/platform/full-stack roles. Cross-direction recommendations are not proof of poor suitability for a candidate's narrower specialization. All people, experience and postings are fictional.
- Validated the three input schemas and verified that all expected readable/JSON artifacts exist and all three final raw Agent responses parse as JSON. The 33 focused tests still pass after adding the batch runner support. No database, migration, commit or push was used.

### 2026-10-18 (America/Chicago) — Three complex fictional résumés

- Added three longer, Review-compatible fictional résumés: backend/data engineering (Avery Example), frontend/full-stack (Taylor Example), and systems/research (Casey Example). Each has two education records, two work entries, three projects, research, publications, awards, certificates and leadership information; readable versions contain approximately 570–640 English words.
- Ran the actual three-stage Agent flow sequentially against the same synthetic JD set. The first case completed in 85.157 seconds; the second in 59.887 seconds. The third initially failed source-path validation, then completed unchanged on retry in 71.097 seconds.
- Bundle: `backend/local_results/skill_gap/complex_resume_cases/20261019T031603Z_e46b61de/`. UTC directory naming crosses into October 19; the local run date is October 18.
- All three final results passed schema, citation/path and numeric/order validation. Each case contains readable résumé, reviewed JSON, full JD copy, three original Agent JSON responses, calculated JSON and report. Shared JD content and demand statistics matched across cases. Failed raw responses remain under `runs/`.
- Actual quality issue: frontend résumé explicitly contains JavaScript/React testing in work and projects, but the Agent omitted those stronger citations and scored both 0.60 through applied evidence. This is not a Python calculation error; completeness is not guaranteed by schema/quote validation.
- Actual quality issue: systems résumé's first extraction cited `/other/0/content/0` although `content` is a string, and treated a negative PostgreSQL experience statement as listed evidence. The invalid path blocked publication. Retrying the unchanged input returned empty PostgreSQL evidence and completed successfully.
- Added a bundle-local `QUALITY_REVIEW.md` with exact source paths/quotes and preserved failure provenance. No output was manually altered to make it match expected higher scores.
- The 33 focused tests still pass. This batch tests the current rules and does not fix their known limitations. No database, migration, commit or push was used.
