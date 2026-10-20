# Structured job-description local experiment (v3)

Setup and current execution commands: [Run locally on another computer](SKILL_GAP_RUN_LOCAL.md).

Latest outcome: the October 20 Agent-configured strict-schema campaign completed all three cases. See the final section below. Earlier prompt-only failures and the per-request `text` override rejection are historical observations, not the status of the latest campaign.

This isolated test uses the configured Skill Gap Azure Agent and the existing three complex fictional Review-page resumes. It does not start FastAPI, import a database session, run a migration, commit, push, or change the remote Agent definition. The old v2 test remains available unchanged.

## Inputs

- Twenty synthetic US software-engineering internship postings across ten fictional companies: four each for backend, frontend, data, systems, and full-stack work.
- Every posting follows the colleague's proposed parsed-JD fields: `job_title`, `company_name`, `job_family`, `seniority`, `department`, `locations`, `role_overview`, `responsibilities`, `qualifications`, `job_conditions`, `compensation`, `benefits`, and `other_relevant_information`.
- Each value/qualification retains evidence. A wrapper holds the local posting ID and independently retained original source, enabling exact-quotation checks against both the parsed JSON and source text. These are new fictional postings, not copies of real vacancies.
- The original Avery, Taylor, and Casey complex reviewed-resume fixtures remain unchanged. Personal contact fields are removed from Agent requests.
- Sixteen catalog criteria standardize cross-posting names. The catalog is not an assertion that every job demands every criterion; only actual Agent extractions contribute to counts.

## Processing

1. Agent maps qualifications to grounded catalog criteria, retaining required/preferred labels and logical groups. Responsibility and work-condition extraction is separate.
2. Python checks each returned posting, exact source pointers/quotations, original-source quotations, labels, and catalog metadata. It compares the extracted criteria to an independent synthetic-fixture oracle before scoring.
3. Python counts each criterion once per posting. Required wins over preferred for the same criterion/posting. Alternative programming languages remain one criterion; twenty mentions of the alternative group do not mean twenty explicit Python requirements.
4. Agent evaluates each resume against the same catalog, returning statuses, matched alternatives and exact citations. One supported option can satisfy an `any_of` requirement.
5. Python checks resume pointers and quotations, scores evidence, and computes gaps. Agent then explains the supplied calculation without altering it. A strict local comparison checks every immutable final field.

The current remote Instructions are used with an explicit per-request invocation contract and JSON schema in the message. This is local validation, **not API-enforced structured output**. A local invocation-contract snapshot and all raw responses are retained in the separate audit directory. The configured remote Instructions were not independently exported/version-pinned.

## Experimental calculation

- `required_ratio = required_postings / 20`
- `preferred_only_ratio = preferred_only_postings / 20`
- `combined_ratio = (required_postings + preferred_only_postings) / 20`
- Evidence: no evidence `0`; listed `0.25`; applied `0.60`; validated `0.80`; validated in at least two independent entries with different quotations `1.00`.
- A `partial` match is conservatively capped at `0.60`. Conceptual coursework without a demonstrated `any_of` option is capped at `0.25` and must not be presented as satisfying the practical requirement. These caps are experiment-specific rules, not calibrated statistical estimates.
- Nontechnical competencies and `needs_confirmation` evidence scores are `null`, not artificial zeroes. Their numeric gap and priority are also `null`.
- `gap = round(combined_ratio * (1 - evidence_score), 6)` when evidence is scored.
- Priority: high `>= 0.60`, medium `>= 0.30`, otherwise low.
- Required and preferred counts are kept separate, but this experiment gives both equal weight in combined demand. This is transparent, provisional, and may not be the right eventual product weighting.
- Missing internship availability or workplace preference remains `needs_confirmation`; a past graduation date does not establish current enrollment or ineligibility.

## Files and execution

Entry point: `backend/scripts/test_skill_gap_structured_local.py`.

Local delivery: `backend/local_results/skill_gap/structured_20_20261020/`:

- `job_descriptions/`: twenty structured source JSON files.
- `resumes/`: three unchanged reviewed-resume JSON files.
- `agent_returns/`: only successfully validated final Agent JSON files.
- `results.txt`: readable result summary and per-criterion calculations/statuses.

Detailed requests, raw responses, catalog, independent expected labels, computed scores and run status remain separately under `structured_20_20261020_audit/`. Both directories are git-ignored. Reruns can reuse identical saved intermediate responses; that provenance is printed. The first initial oversized request was rate-limited, so the runner uses batches of two and an explicit output-token budget.

## Limitations

All inputs are fictional. Twenty mixed-track postings are neither a representative market sample nor a personalized set of role recommendations; confidence remains low. Cross-track gaps must not be described as general unsuitability. Exact citation checks and a fixture oracle do not guarantee correct semantic resume assessment or exhaustive evidence selection. Evidence scores are not measured ability, and gap scores are not hiring probabilities. Natural-language claims and recommendations require review.

## Observed quality issues in the October 20 run

- The first larger requests were rate-limited. Smaller batches with an explicit output budget succeeded; all twenty actual JD extractions matched the independent expected labels.
- Avery's generic cloud-course certificate produced partial concept evidence with no matched platform. The initial local guard was too strict about partial matches. The guard now distinguishes full satisfaction from conceptual exposure, with a dedicated regression test and a maximum score of `0.25` for the latter. The original response is preserved; no platform experience was invented.
- Taylor's initial response marked Linux `not_evidenced` while returning `matched_options: ["Linux"]`. It was rejected and the actual Agent was asked again, not patched locally.
- Several final responses were invalid JSON (missing braces/trailing commas); an earlier 8,000-token response was truncated. Failed responses remain in the audit folder. Final responses are accepted only after parsing and comparison with Python-calculated immutable fields; malformed JSON is not silently repaired.
- Evidence completeness is still a substantial limitation. For example, Avery's programming evidence score is `0.60`, although `/work_experience/0/content/1` and `/research_experience/0/content/1` explicitly describe executed Python tests. Taylor's web-UI evidence is `0.60` despite explicit React tests in `/work_experience/0/content/1` and `/projects/0/content/1`. Casey's programming/systems extraction likewise omits stronger Python/Rust testing citations. These omissions can underestimate evidence and inflate a computed gap. The raw Agent evidence and resulting scores were not manually changed.
- Avery's summary groups Python/JavaScript as programming strengths, but the cited JavaScript evidence is only a seminar/listing. The correct interpretation is strong Python application plus weaker JavaScript exposure, not independently proven JavaScript competence.

A future reliability improvement is a task-specific API response-format schema where supported, rather than only a schema inside the prompt. Microsoft documents the Responses API's `text.format` mechanism in its [structured-output section](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses#structured-outputs). This run does not enable that mechanism or change the Agent's portal settings.

## API-level schema compatibility check — 2026-10-20

- Added genuine `text.format = {type: "json_schema", strict: true, name, schema}` request support, keeping the three separate task schemas and existing local semantic/numeric validation. Unknown/null fields retain their schema types.
- Added completion status, refusal, token-usage, incomplete-response and returned-format metadata. Incomplete/refused responses fail before being accepted as usable JSON. Rejected API schema requests never silently fall back to prompt-only output.
- A **fresh** replay of Casey's existing final-stage input was rejected twice by the configured bound Azure Agent endpoint. The detailed response is `400 / invalid_payload`, parameter `text`, message **"Not allowed when agent is specified."** This is an endpoint restriction before output generation, not an Agent JSON syntax failure and not a successful strict-schema replay.
- Evidence: `backend/local_results/skill_gap/api_schema_replay_20261020T184430Z/response_metadata.json`. Earlier malformed Agent responses and the 2-pass/1-fail batch remain unchanged.
- The main v3 runner preserves its original prompt-only default. `--api-json-schema` explicitly requests strict API mode and fails closed if the endpoint rejects it. The separate `scripts/retry_skill_gap_api_schema.py` always requests strict mode; it does not use cached output or change cloud settings.
- **API-level schema has not been successfully enabled on the current Agent endpoint.** Enabling a fixed schema on separate cloud agents or switching to direct underlying-model calls requires a further user choice; neither was performed.
- All 57 focused local unit/regression tests pass. These tests verify request construction and error handling, not provider support. No database, cloud Agent edit, commit, push or PR.

## Agent-configured unified schema — full rerun, 2026-10-20

The user configured `docs/testing/skill-gap-response-format.json` on the existing Azure Agent and updated its Instructions. The local caller does not send the forbidden per-request `text` or `reasoning` overrides. It validates `response.task` plus `response.data` using the corresponding local task model. Returned provider metadata confirms strict `careergps_pipeline_response` JSON Schema, unlike the earlier prompt-only experiment.

Delivery: `backend/local_results/skill_gap/structured_schema_20261020_200k/`. It contains only 20 JD JSON files, three unchanged resume JSON files, three original enveloped final Agent JSON files, and `results.txt`. Detailed evidence and attempts are in the separate `_audit` sibling.

- All twenty postings were freshly processed in batches of two, and independent fixture expectations matched exactly. All three resumes' evidence and final stages were freshly invoked. No previous batch's statistics or scores were substituted.
- The campaign resumed once after a JD citation failure; it retained the first two successfully generated postings from this same campaign. The earlier subrun manifest is preserved. Across both subruns: **22 real calls**, all completed, all strict-schema, all valid JSON; **zero rate limits, truncations or refusals**. Five JD replies required correction of paths/source fields. One resume reply was unnecessarily rejected by an overbroad local negation guard, not by the provider or JSON parser.
- All three cases passed final immutable-field comparisons: Python's counts, ratios, evidence scores, gaps, priorities, evidence and ordering were unchanged. **65 focused tests pass.** No database was used, no cloud setting was edited by the test, and nothing was committed or pushed.
- Output allowance is now configurable (`--output-token-budget`, envelope default 25,000) and includes reasoning. Envelope calls allow 300 seconds; legacy calls retain their 120-second default. Earlier 5,000-token attempts exhausted the allowance on reasoning alone. Higher TPM and sufficient per-call output allowance address different limits.

### Human-reviewed quality: not production-ready scoring

The original Agent returns and calculated numbers were retained without manual score corrections:

- Avery: SQL increased from 0.60 to 0.80, but a second independent SQL-test citation is still omitted. Programming and PostgreSQL remain 0.60 despite explicit Python and PostgreSQL testing in the source. Its programming explanation incorrectly says JavaScript was applied in projects/internship; the cited JavaScript evidence is a seminar only. It also discusses language breadth although the programming requirement is `any_of`, not all languages.
- Taylor: programming and React remain 0.60 although explicit JavaScript/React tests appear in two independent entries. Those test citations were used for testing but not for their underlying skills. Relational-database implementation rose from 0.25 to 0.60 using a Postgres listing plus SQL queries, which do not establish that PostgreSQL persistence/schema implementation was demonstrated. Data-structure evidence at 0.60 uses SQL/data-import quotes without explicit data-structure implementation; algorithm evidence also needs review rather than treating generic tests as proof of algorithm design.
- Casey: programming/systems remain 0.60 despite explicit Python/Rust test evidence. Testing fell from 1.00 to 0.80 because several explicit test executions were categorized `applied` rather than `validated`. Algorithm evidence at 0.80 is inferred from metric-aggregation tests, not a direct algorithm-design claim. Its programming explanation cites missing API/frontend work, which belongs to separate criteria and is not a reason to discount satisfying an alternative-language group.
- Casey's rejected paragraph correctly supported SQLite while explicitly denying PostgreSQL experience; only SQLite was in `matched_options`. The blanket negation regex rejected the whole paragraph. The actual retry shortened it to `SQL work used SQLite` and passed. Future validation should scope negation to the claim/clause, not reject unrelated positive evidence in the same paragraph.

Conclusion: **structural reliability improved, but semantic evidence selection/categorization and explanation fidelity remain inconsistent**. Exact quotes do not prove a category is justified. Correct Python arithmetic does not make an unreliable input assessment accurate. These synthetic mixed-track evidence gaps are not proficiency measurements, personalized role suitability, or hiring probabilities.
