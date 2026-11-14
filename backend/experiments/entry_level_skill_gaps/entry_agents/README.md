# Entry-level Agent scoring and compact assessments

This directory packages two historical, isolated experiments. It is not imported
by application routes and does not select or update the application's Agents.
All-job skill demand was retained. The recorded AI Engineer demand denominator
was 566 jobs, without filtering for seniority.

## Contents and versions

- `entry_contract.py`: initial entry-level criteria plus the original evidence
  record. The three files in `prompts/` are archived initial entry-level prompts.
- `compact_contract.py`: compact criterion output with a shared proof pool.
  `build_instructions(group)` generates its compact prompts.
- `criteria.json`: 63 skill cards across three job families, with three criteria
  per skill. The historical live tests cover only 23 AI Engineer skills.
- `scoring_policy.json`: fixed weights/status policy. Scores remain experimental
  evidence-coverage measures, not validated ability or hiring-probability estimates.
- `run_experiment.py`: local payload preparation and saved-response scoring, plus
  an explicitly selected live invocation helper.
- `manage_agents.py`: offline Agent-plan export; optional new-name provisioning.
- `test_contracts.py`: synthetic reference, linkage, arithmetic and opt-in checks.
- `results.json`: historical aggregate measurements, including pending states and
  limitations. Private resumes, raw responses and machine paths are not included.

The initial rubric uses core, method and check criteria weighted 0.5, 0.3 and 0.2.
Supported/partial/not-evidenced map to 1/0.5/0. A non-supported critical criterion
caps a resolved skill score at 0.6. Any uncertain or invalid criterion leaves the
skill pending. A pending skill is not converted to zero, and the existing match
calculation excludes it from the scored denominator. Coursework, research,
projects and internships can qualify when the required personal work is stated.

The compact change removed the legacy evidence record, introduced explicit
criterion basis and strengthened same-activity linkage for practical method/check
criteria. The criterion text and numeric weights stayed fixed, but validation
semantics changed. This was not a pure serialization or output-length experiment.
Exact quotes and valid activity IDs do not establish semantic entailment or prove
that two statements concern the same workload.

## Historical results

Both experiments used the same confirmed AI Engineer resume, with three formal
repetitions per condition and three parallel group calls per repetition. These
were not three independent applicants. Software Engineer and Data Analyst were
not live-tested in these comparisons.

| Comparison | Mean scoring-stage wall time | Displayed weighted matches |
| --- | --- | --- |
| Original rubric, first experiment | 55.677 s | 43.32%, 41.84%, 44.77% |
| Initial entry rubric, first experiment | 87.078 s | 70.02%, 77.28%, 76.27% |
| Entry v1, fresh compact comparison | 61.164 s | 77.45%, 73.62%, 71.86% |
| Compact v2, fresh compact comparison | 36.015 s | 62.29%, 78.93%, 73.32% |

The fresh compact comparison reduced mean wall time by 41.12%. This does not
establish better accuracy. It changed prompt, schema and validation together;
pending coverage and evidence selection also changed. Initial entry scores have
a different meaning from original-rubric scores. A higher number is not evidence
of improved applicant ability. Request/cache variation prevents using a mean
from one experiment batch as a fixed control for another batch.

Times include client/authentication, conversation creation, inference, cleanup
and local scoring; preparation and provisioning are excluded. The first
experiment contains 18 formal calls plus a separately recorded three-call
instrumentation pilot. The compact comparison contains 18 fresh calls. Historical
semantic quality was not fully accepted and neither experiment was promoted.
Packaging these files did not repeat any live call.

## Offline use

Run commands from `backend/` with the repository's Python dependencies installed.
Offline commands and tests do not import Azure clients or read Azure credentials.

```sh
python -m unittest experiments.entry_level_skill_gaps.entry_agents.test_contracts -v
```

The input for `prepare` is the existing prepared Skill Gap input contract with
`job_family` and complete `resume_sources`. No private default input is bundled.

```sh
python -m experiments.entry_level_skill_gaps.entry_agents.run_experiment prepare --variant compact --group foundation --input /path/to/prepared_resume.json --output /path/to/new_payload.json
python -m experiments.entry_level_skill_gaps.entry_agents.run_experiment score --variant compact --input /path/to/new_payload.json --response /path/to/saved_response.json --output /path/to/new_assessment.json
```

Use `--variant entry` for the initial contract. Outputs use exclusive creation;
existing files are never overwritten. Validation reports retain errors and
pending states rather than repairing a response. These commands do not change
the runtime market snapshot or calculate a different demand cohort.

Later experiments can reuse these Python functions:

```python
from experiments.entry_level_skill_gaps.entry_agents.run_experiment import (
    invoke, read, save_new, weighted_entry,
)
```

`invoke(payload, agent, folder, endpoint, group="diagnostic")` returns parsed output
and timing/token metrics. Calling this function explicitly requests one live call;
it requires a numeric pinned Agent version. `weighted_entry(rows, market, family)`
applies supplied all-job weights only and must not be used to claim a full-resume
match from a deliberately restricted diagnostic subset.

The local score command also accepts `--adapter package.module:function` for a
trusted function inside `experiments.entry_level_skill_gaps`. The function receives
`(response, payload)`. This permits later diagnostic schemas without duplicating
the live transport or silently applying the compact validator to another schema.

## Explicit live use

No command creates an Agent or invokes a model by default. First export a plan:

```sh
python -m experiments.entry_level_skill_gaps.entry_agents.manage_agents --variant compact --group foundation --model YOUR_DEPLOYMENT --output /path/to/new_plan.json
```

Adding `--create --endpoint YOUR_HTTPS_PROJECT_ENDPOINT` explicitly provisions one
new Agent and writes a usable pinned configuration. Its name includes a random
run suffix under `skill-gap-experiment-`. Existing names are rejected; application
Agent names cannot be used. There is no update or application-configuration path.
Inspect the result before deciding whether to run it. Do not commit generated
bindings or configuration containing a real project endpoint.

`config.example.json` is a placeholder-only template. A real configuration can
include `agent.definition`; if supplied it must equal the pinned live definition.
Without it, the pinned definition is read before the call and its hash is recorded.

```sh
python -m experiments.entry_level_skill_gaps.entry_agents.run_experiment live --live --config /path/to/private_config.json --input /path/to/payload.json --output /path/to/new_run_directory
```

Live output directories contain private inputs and raw responses. Keep them in
ignored local output storage. There are no automatic retries, repairs or changes
to saved Agent definitions. A temporary conversation is deleted after the request;
cleanup failure is recorded. Model, reasoning and output-contract metadata are
checked against the pinned definition. This portable runner has been checked
offline; its new provisioning/transport wrapper was not live-tested during
packaging. The historical times above belong to the original recorded runners.
