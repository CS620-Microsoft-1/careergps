# Scoring stability and explicit evidence rules

This isolated package preserves four stages of the entry-level experiment:
prompt stability, fixed activity/core evidence, explicit rules v1, and the v1.1
Python-detail clarification. None is connected to the application workflow.
All stages retain the all-seniority job-demand snapshot. The historical AI
Engineer denominator is 566 jobs. Demand weights do not determine evidence
labels or individual grades.

The first two stages assess all 23 AI Engineer skills through the Foundation,
Lifecycle and Systems groups. Rule calibration covers only Python, LLM and
Agents as three skills. It does not replace all three business Agents or
calibrate the remaining 20 skills.

## Files

| File | Purpose |
| --- | --- |
| `prompt_variants.py` | Historical prompt-stability v3 and explicit rule v1/v1.1 instructions |
| `fixed_evidence.py` | Full-activity packet construction, core-anchor requirements and separate scope audit |
| `rule_contract.py` | Three-skill request, response schema, source checks and deterministic scores |
| `cases.json` | 18 original synthetic cases and 4 later wording probes, with provenance and expected labels |
| `test_experiments.py` | Offline checks using synthetic sources only |
| `results.json` | Sanitized historical measurements and retained failures |

The original private resumes, source paths, cloud bindings and raw run trees
are not packaged. Historical measurements are retained, not rerun or repaired.
The snapshot fingerprints identify the source result artifacts. Tests of this
portable package validate its contracts; they are not new live-model evidence.

## Offline use

Run from the repository's `backend` directory after installing its Python
dependencies. None of these commands loads Azure credentials or calls a model.
The output directory is local and ignored by Git. Each command refuses to
overwrite an existing output file.

```console
python -m unittest experiments.entry_level_skill_gaps.stability_rules.test_experiments -v
python -m experiments.entry_level_skill_gaps.stability_rules.rule_contract prepare --version v1.1 --output experiments/entry_level_skill_gaps/.local/rule_request.json
python -m experiments.entry_level_skill_gaps.stability_rules.rule_contract score --input experiments/entry_level_skill_gaps/.local/rule_request.json --response experiments/entry_level_skill_gaps/.local/saved_response.json --output experiments/entry_level_skill_gaps/.local/rule_report.json
```

The `score` command requires an actual previously saved response. It does not
construct model answers from `expected_criteria`. For the adapted historical
control, pass `--mode control`. The `v1` case set has 18 entries; `v1.1` has 22.

The shared `entry_agents.run_experiment` runner can also score with
`--adapter experiments.entry_level_skill_gaps.stability_rules.rule_contract:score_response`.
That adapter uses the explicit-rule validator shared by v1 and v1.1, not the
adapted control's broader partial-credit rules.

## Preparing other variants

`prompt_variants.build_instructions(variant, group=None)` supports:

- `prompt_stability`, with `foundation`, `lifecycle` or `systems`: the v3 prompt
  with the unchanged compact response schema and numeric policy.
- `fixed_evidence`, with a group: compact judgments plus packet restrictions.
- `control`, `rules_v1`, `rules_v1_1`, without a group: a three-skill batch using
  `rule_contract.output_format()` and `rule_contract.build_payload(cases)`.

For fixed evidence, first create the normal compact group payload with the
stage-2 builder. Call `fixed_evidence.build_payload(compact_payload, packet)`.
The packet's `skills` mapping contains, for every assigned skill, an
`activity_id`, all that activity's `unit_ids` in their original order, and one
or more `anchor_unit_ids`. The optional `resume_sources_sha256` binds the
original source list. Packet annotations, expected scores and notes are not
forwarded. Whole selected activities retain their original text and IDs.

Score fixed responses with `fixed_evidence.assess_output`, and separately call
`fixed_evidence.audit_compliance`. The scope audit does not silently rewrite
the original scores. It also does not prove semantic eligibility. c2/c3 source
choices and quotes remain model-selected inside the fixed activity.

All variants reuse `entry_agents.run_experiment.invoke(payload, agent, folder,
endpoint)` for an explicitly requested, pinned live call. There is no duplicate
cloud runner here and no live call on import. A caller must supply an isolated
Agent binding with matching prompt/schema, an explicit endpoint, a new local
output directory and separately approved input. The generic runner does not
change an Agent or choose the variant for the caller. Historical timing
excludes evidence preparation and Agent provisioning.

## Explicit scoring standard

This is an experimental product convention, not an employer-validated scale.
Coursework, personal projects, research and internships can qualify. Production
scale, business impact, advanced architecture, multiple tools, full autonomy
and numerical improvement are not required unless a criterion explicitly says
otherwise. A high grade describes evidence under these entry-level rules, not
mastery or hiring probability.

| Criterion | Points | Decision |
| --- | --- | --- |
| c1: qualifying personal practice | 50 or 0 | Personal contribution, skill identity and a stated task must be established. No partial credit. Genuine ownership/identity/linkage ambiguity remains pending. |
| c2: implementation detail | 30 or 0 | One relevant concrete operation, input/output detail or control step in the same example is sufficient. No partial credit. |
| c3: actual check | 20, 10 or 0 | An executed check with a case, requirement, comparison, error, diagnostic observation or constraint earns 20. An explicitly performed check without those details earns 10. A plan, intended purpose or unrelated check earns 0. |

Any uncertain criterion or invalid reference leaves the whole skill pending.
It is not converted to zero. When c1 is absent or uncertain, c2/c3 receive no
standalone credit; this does not prove those behaviors never happened. Missing
method/check details do not erase supported core practice. c2 and c3 are
independent once c1 is supported. Same activity ID does not prove same workload.

Only one allowed alternative is required: an OR list is not an AND checklist.
One sufficient source statement may support both c1 and c2. The rules do not
require a code excerpt, an exact API name or enough detail to reproduce a full
implementation. Bare skill listings cannot establish the practical evidence
required by these three cards.

### Skill boundaries

- Python: personal Python implementation or a permitted Python-library route
  for a stated task. An explicit OpenCV/PyTorch video-development workflow can
  qualify without repeating the literal word Python. A finished tool's
  implementation language, teammate-only code or an explicitly C++-only
  implementation does not establish the applicant's Python practice.
- LLM: personal use/development with an identified language model for text
  understanding, generation, transcription or structured information
  extraction. A multimodal language model can qualify when the language
  function is explicit. Generic AI work or pure image classification does not.
  One input, output, prompt, context or integration detail can support c2.
- Agents: personal design/implementation AND a model-mediated tool/action
  workflow AND (invocation OR result handling OR control flow). One bounded
  tool with human approval qualifies. A name, retrieval, rules, logs, retries
  or review routing alone does not establish model-mediated control. Explicit
  fixed rules without model involvement are ineligible; unresolved model
  involvement in a relevant workflow remains uncertain.

In v1.1, Python c2 explicitly separates a task category from an operation:
using pandas for data preparation alone earns c1 only (50). Removing rows with
missing customer IDs also establishes c2 (80), if neither example supplies a
check. This clarification does not tighten the LLM or Agents alternatives.

For c3, a workflow built for evaluation is not evidence that evaluation ran.
An adjacent implementation requirement is not automatically the criterion
used by an unspecified test. A statement such as "tested this implementation"
earns only partial checking credit unless its check is explicitly connected
to a case, expectation, comparison, error, observation or constraint.

The unchanged grade mapping is A at 90-100, A- at 80 to below 90, B+ at 70 to
below 80, B at 60 to below 70, C at 40 to below 60, D above 0 to below 40, and F
at 0. Pending has no grade. Under the current binary c1/c2 gates some intervals
are unreachable; the mapping is retained for compatibility. F means no
qualifying positive evidence in this material, not inability.

## Historical results and retained failures

| Experiment | Main repeats per version | Main timing | Stability result |
| --- | --- | --- | --- |
| Prompt stability v2 vs v3 | 5 | Mean 37.772 vs 53.229 seconds | Varying criteria 27/69 vs 24/69; 15/23 skill scores or pending states varied in both |
| Free vs fixed activity/core anchor | 5 | Mean 51.847 vs 49.407 seconds | Varying criteria 23/69 vs 24/69; varying skill scores/pending 13/23 vs 15/23 |
| Three-skill adapted control vs rule v1 | 5 | Mean 15.314 vs 8.102 seconds | Main varying criteria 4/9 vs 0/9, but one of 18 short cases still varied |
| Rule v1.1 main regression | 3 | Mean 8.267 seconds | LLM scores 80, 90, 80; semantic stability gate failed |

The first two comparisons each used 42 live calls, including two repeats per
version on a historical synthetic resume. Rule calibration used 16 initial
calls and 9 follow-up calls. All-job demand remained unchanged. Aggregate
matches in the 23-skill experiments exclude pending skills; changes in those
denominators can affect the reported match. Higher scores are not accuracy.

The fixed-evidence experiment had no scope-ID violations in 161 skill/run
instances, but two of 281 literal references had wrong quoted text. Their
affected scores stayed pending. Fixed sources did not prevent missed practice,
unrelated-workload checks or purpose-as-check interpretations. Full offline
packet preparation/review time was not recorded, so the modest inference-time
difference is not an end-to-end speedup claim.

Rule v1 repeated Python 80, LLM 80 and Agents pending five times on the known
resume. Its generic Python task case still yielded 80, 50, 50. The v1.1
clarification retained that failure and added four wording probes. On the
same extended 22-case batch, both v1 and v1.1 matched all 198 expected criterion
judgments across three rounds. This did not establish an advantage for v1.1.

In the final real-resume regression, Python stayed at 80 and Agents stayed
pending. LLM produced 80, 90, 80. The 90 awarded partial checking credit to
evaluation-purpose wording without an executed check. The source IDs and
arithmetic were valid; the semantic decision was wrong under the frozen
rules. The raw failure was retained, not repaired or rerun until success.
There is no evidence that the Python clarification caused this LLM error.

The short cases are agent-authored analytical fixtures, not human-adjudicated
gold labels or a blind benchmark. Main evidence was already known during rule
design. Structural tests, valid IDs, repeated agreement and fixture agreement
do not establish general accuracy. These results support further review of the
rules and their execution; they do not justify production promotion.
