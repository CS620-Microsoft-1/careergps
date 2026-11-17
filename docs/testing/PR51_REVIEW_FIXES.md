# PR #51 review fixes

These follow-up changes are ready for local review. They have not been committed,
pushed, or added to the remote PR description.

- PR branch: `test/entry_level_skill_gaps`.
- Base HEAD: `1b895db0c0789b5a60bba5659bd8716f0cc6ac2c`.
- Tested source: that HEAD **plus the uncommitted changes in this checkout**.
  The base SHA alone does not include these fixes. Record the new commit SHA
  after review and commit; do not label the base SHA as the tested fix commit.

## Changes for review

1. **Pipeline evidence permissions.** Recovery now applies the occupation's
   normal `_candidate()` rules to c2/c3 in both newly recovered and already
   selected activities. It preserves the three-activity cap, omission status,
   source ordering and diagnostics. `SELECTOR_VERSION` is now
   `entry-level-criterion-activity-recall.v2`. Controlled production-path tests
   score complete AI/DA examples at 100 and the corresponding examples without
   an executed check at 80; an unauthorized c3 citation remains pending.
2. **Reproducible Agent definitions.** The repository contains all nine exact
   instructions, response formats and complete definition options, with model,
   reasoning, source versions and SHA-256 hashes in a manifest. The loader
   checks the response formats against production `build_format()`. The
   management script supports offline `check`, idempotent `create`, and remote
   `verify`. A conflicting saved definition stops creation without replacement.
3. **Formal Azure bindings.** All nine formal `careergps-entry-level-{ai,se,da}-`
   Foundation/Lifecycle/Systems Agents were created in Azure and read back
   successfully **before** changing the local runtime bindings. Each is pinned
   to saved version `1`. The original experiment-named Agents were preserved.
   Their complete definitions are unchanged. The SE Systems instructions hash
   also corrects a typo in the old pin; its actual instructions were not changed.
4. **Visible workflow selection.** `.env.example` explicitly chooses
   `entry_level`, with legacy bindings commented in their own section. The
   backend records requested mode, effective workflow and selection reason in
   its log and each new run's `workflow_selection.json`. Tests cover explicit
   modes, approved/unapproved projects, whitespace and version-only legacy
   settings. The API/report/database formats are unchanged.
5. **Direct production-rule tests.** Added coverage for weights, allowed partial
   credit, critical caps, zero versus pending, citation integrity and permissions,
   same-activity evidence, selection limits, Systems facts/dependencies, bundled
   definitions and remote preflight. All tests are under `backend/tests/` and
   therefore included by the existing backend CI discovery command. The new
   tests use fixed data and mocked responses, with no Azure calls.
6. **Documentation and import fix.** The backend README explains all-level demand
   weighting, the small entry-only samples, the fixed model, synthetic-resume
   limitations, and the division between Agent judgment and Python validation/
   calculation. Job-scope tests now support both package and directory discovery.

See the [backend README](../../backend/README.md#skill-gaps-with-authenticated-resumes)
for setup and the [manifest](../../backend/app/prompts/skill_gaps/entry_level/manifest.json)
for all nine exact bindings.

## Offline validation

| Check | Result |
| --- | --- |
| Full backend discovery | **768 total: 729 passed, 39 skipped, 0 failures/errors** |
| Five new rule/selector/Agent/transport test modules | 66 passed; included in the full total |
| Additional workflow tests in the existing run module | 3 added; included in the full total |
| Job-scope package invocation | 5 passed |
| Job-scope directory discovery | The same 5 tests passed |
| Bundled Agent check | 9 definitions validated offline |
| Azure management-script verification | 9 formal saved Agents verified |
| Whitespace check | `git diff --check` passed |

PostgreSQL-dependent tests account for the 39 skips; they were not exercised
against a live test database. Backend tests completed in 18.544 seconds in this
environment. The new modules and workflow additions add 69 discovered tests.

Reproduction commands, from `backend/`:

```powershell
python -X utf8 -m unittest discover -s tests -v
python -X utf8 -m unittest experiments.entry_level_skill_gaps.job_scope.test_scope -v
python -X utf8 -m unittest discover -s experiments/entry_level_skill_gaps/job_scope -p test_scope.py -v
python scripts/manage_entry_level_agents.py check
python scripts/manage_entry_level_agents.py verify --endpoint <project-endpoint>
```

The recorded full run used `unittest.defaultTestLoader.discover('tests')` and
`TextTestRunner(verbosity=2)` through a local bootstrap that set a writable
temporary directory and a dummy local `DATABASE_URL`. This is the same discovery
as the first command above. UTF-8 mode is necessary on this Windows environment
because some existing fixture readers otherwise use its GBK default. The first
non-UTF-8 run encountered three fixture decoding errors; the UTF-8 run passed.
CI uses `python -m unittest discover -s tests -v` on Ubuntu.

## Live verification

All nine original definitions were first checked against their approved complete
definition hashes. Their formal replacements were then created, read back,
verified with the checked-in management script and used by the production
preflight and run manager. No instructions or model parameters changed during
these calls. The smoke runs used synthetic evidence and local JSON storage;
they did not write student data or reports to PostgreSQL.

| Occupation / attempt | Result | New model calls | Elapsed | Pipeline score |
| --- | --- | ---: | ---: | --- |
| AI Engineer, initial | Blocked: unsupported RAG fact claim lacked proof | 3 | 33.06 s | No final report |
| AI Engineer, retry | Completed; 6 skills pending | 2 | 31.66 s | 100 |
| Software Engineer | Completed; 3 skills pending | 3 | 41.88 s | Not in this catalog |
| Data Analyst | Completed; no skills pending | 3 | 27.08 s | 100 |

The AI retry reused one valid cached branch and called the other two. An
intermediate submission reused the failed run without any new model calls; it
was not a separate model attempt. Validation was not relaxed to obtain the
completed report. Completed reports can still contain pending skills and are
not evidence that every model judgment is correct. These timings are smoke-test
observations, not a before/after performance benchmark.

Local audit artifacts are retained outside the checkout in
`D:\cs620 proj\tmp\pr51-validation`, including `backend-tests-utf8.log`,
`azure_migration.json`, `azure_verified.json`, `agent-cli-verify.log`,
`live_summary.json`, and per-run preflight, response and assessment files.

Completed run IDs:

- AI Engineer: `17d91320c37740e4aaf6f9689810f9a1`.
- Software Engineer: `52e0a634b0ea4888a1e685222827f11e`.
- Data Analyst: `6b309e1d295a4fcabb84d9d4332af1fa`.

## PR validation text prepared for publication

After committing and pushing the reviewed changes, replace the PR's stale test
count with the following and add the actual fix commit SHA:

> Backend regression discovery recorded 768 tests: 729 passed and 39
> PostgreSQL-dependent tests skipped. The job-scope suite passed all 5 tests from
> both package and directory invocation. All nine repository Agent definitions
> matched their schemas and hashes, and all nine formal Azure Agents passed
> remote verification and production preflight. Live synthetic runs completed
> for AI Engineer, Software Engineer and Data Analyst. The first AI attempt was
> blocked for an unsupported RAG fact claim; one retry completed without changing
> the definitions or weakening validation. AI and DA live Pipeline examples
> scored 100; fixed-response regression cases without check evidence scored 80.

The earlier ten-resume comparison remains historical evaluation evidence; it
was not rerun as part of this follow-up. Do not describe the new smoke timings
as an updated ten-resume benchmark or the local tests as a remote CI result.
