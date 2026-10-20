# Run the current Skill Gap experiment on another computer

Use branch **`test/skill-gaps`**. This is an isolated prototype, not an API endpoint or database integration. It reads three fictional reviewed resumes, generates twenty fictional structured JDs, invokes the existing Azure Agent, computes scores in Python, and saves results locally.

## 1. Get this branch

For a new checkout:

```powershell
git clone --branch test/skill-gaps --single-branch https://github.com/CS620-Microsoft-1/careergps.git
cd careergps/backend
```

For an existing checkout, first preserve any local changes, then fetch, switch to `test/skill-gaps`, and pull with `--ff-only`. Do not reset or overwrite other local work to follow this guide. Do not merge or push this experiment into `dev` or another branch.

## 2. Install the isolated dependencies

Use Python 3.12. The following Windows commands do not require activating the environment:

```powershell
py -3.12 -m venv .venv-skill-gap
.\.venv-skill-gap\Scripts\python.exe -m pip install -r requirements-skill-gap.txt
```

On macOS/Linux use `python3.12 -m venv .venv-skill-gap`, then `.venv-skill-gap/bin/python` for every Python command below. No OCR system packages or database services are needed for this runner.

## 3. Configure the environment

If `backend/.env` does not exist, copy the provided template:

```powershell
Copy-Item skill-gap.env.example .env
```

If it already exists, **do not overwrite it**. Add or update only these two lines:

```dotenv
SKILL_GAP_FOUNDRY_PROJECT_ENDPOINT=https://sliu965-4101-resource.services.ai.azure.com/api/projects/sliu965-4101
SKILL_GAP_FOUNDRY_AGENT_NAME=olive-agent-nybsd72mqb
```

These are resource identifiers, not authentication credentials. The Skill Gap settings do not require `DATABASE_URL`. Do not copy database passwords, API keys, your `.azure` directory or login tokens between computers. Never commit `.env`.

Install Azure CLI separately if needed, then authenticate on the new computer:

```powershell
az login
```

Use an account authorized to invoke this existing Foundry project/Agent; `az login` alone does not grant project access. If you see authentication/permission failures, verify the account/tenant and ask the project owner to grant access. The runner uses the existing Azure credential chain, so unrelated Azure credential environment variables can also affect which identity is selected.

The existing remote Agent must retain the user's current Instructions and strict unified schema named `careergps_pipeline_response`. The schema is versioned in [skill-gap-response-format.json](skill-gap-response-format.json). This runner does not edit the remote Agent, its quota or model. Cloud Instructions are not exported/version-pinned in this repository. The historical [v2 prompt](../skill-gap-agent-prompt.md) belongs to the old scripts; do not replace the current Agent Instructions with it.

## 4. Run offline checks first

```powershell
.\.venv-skill-gap\Scripts\python.exe -m unittest tests.test_skill_gap_api_schema tests.test_skill_gap_structured_local tests.test_skill_gap_local tests.test_skill_gap_extraction
.\.venv-skill-gap\Scripts\python.exe -m scripts.test_skill_gap_structured_local --agent-envelope --prepare-only
```

The 65 focused tests need no real Agent or database connection. Some negative-case tests intentionally print `FAILED`; the final unittest summary must say `OK`. `--prepare-only` creates/validates the twenty JD and three resume input files without invoking Azure.

## 5. Run the complete live pipeline

From `backend`:

```powershell
.\.venv-skill-gap\Scripts\python.exe -m scripts.test_skill_gap_structured_local --agent-envelope --job-batch-size 2 --output-token-budget 25000
```

The default creates a fresh timestamped directory, so previous runs are not reused. All JD batches are extracted first; Python verifies their citations and compares the synthetic requirement sets with independent fixture expectations. The same fresh market counts are then used for all three resumes. For each resume the Agent extracts evidence, Python computes scores, and the Agent explains that fixed result.

Live calls use Azure quota and may incur charges. The last complete campaign took roughly 31 minutes including retries; that is an observation, not an ETA. The output allowance includes reasoning, and the local request timeout is 300 seconds. Do not use `--api-json-schema` or `--reasoning-effort` with this bound Agent: the tested endpoint rejects per-request overrides. Use the Agent-configured schema via `--agent-envelope`.

If intentionally resuming an interrupted run, supply its existing `--output-dir`. The runner can reuse validated responses whose request matches; this is **not** a fresh rerun. Preserve rejected responses/audit files and check the manifest rather than treating partial output as success.

## 6. Find the output

Under `backend/local_results/skill_gap/structured_20_<UTC timestamp>/`:

- `job_descriptions/`: twenty synthetic structured JD JSON files.
- `resumes/`: the same three fictional reviewed resume JSON files.
- `agent_returns/`: three original final JSON responses, when all cases pass.
- `results.txt`: summary, evidence scores, demand counts/ratios and gap scores.

Successful final responses have the shape `{"response":{"task":"explain_skill_gaps","data":{...}}}`. The separate sibling directory ending `_audit` stores requests, intermediate/raw responses, attempts, calculated facts, returned schema metadata and `run.json`. Failed stages are recorded rather than fabricated. Runtime results, `.env` and virtual environments are git-ignored and are not included in the branch.

## Interpretation and limitations

Evidence: absent `0`, listed `.25`, applied `.60`, validated `.80`, at least two independent validated contexts `1.00`; partial matches have caps. Nontechnical/unknown scores remain null. Python calculates `combined_ratio = (required + preferred-only postings) / 20` and `gap = combined_ratio * (1 - evidence_score)`. Required and preferred counts are displayed separately but currently weighted equally.

The last strict-schema campaign completed all three cases and all twenty JD requirement sets matched fixture expectations. That does not establish accurate skill assessment: the Agent still omits stronger Python/React/Rust test evidence, sometimes over-infers other skills, and can produce unsupported explanation claims. A conservative local negation rule also falsely rejected a mixed paragraph containing positive SQLite and negative PostgreSQL claims. These known issues remain visible; scores were not manually corrected.

See [current v3 rules and reviewed findings](SKILL_GAP_STRUCTURED_LOCAL_V3.md) and [execution history](SKILL_GAP_LOCAL_TEST_PLAN.md). Older v1/v2 scripts and documents remain for history; their inputs/output contracts differ and they are not the recommended entry point for the current schema-configured Agent. The examples are fictional, mixed-track and low-confidence. Scores are evidence-coverage heuristics, not measured ability or hiring probability.
