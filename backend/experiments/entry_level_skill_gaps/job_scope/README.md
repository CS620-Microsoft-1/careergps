# Job seniority scope experiment

This offline experiment changes which existing job-analysis rows contribute to
skill demand. It keeps previously scored resume evidence frozen. It does not
create Agents, call a model or database, or change application configuration.

The cohorts are:

| Cohort | Existing seniority labels | Software Engineer | AI Engineer | Data Analyst |
| --- | --- | ---: | ---: | ---: |
| All levels | No seniority filter | 2,858 | 566 | 174 |
| Entry only | `new_grad`, `entry_level` | 71 | 8 | 2 |
| Entry plus intern | `new_grad`, `entry_level`, `intern` | 187 | 30 | 19 |

The original source had 3,715 parent postings. Entry-only selection contained
82 parent rows, of which one had no supported job family. Entry plus intern
contained 238 parent rows, of which two had no supported family. Unknown and
mixed-level labels are excluded by exact matching. No date or geography filter
is added. The exported seniority labels are reused, not semantically rechecked.

## Files and provenance

- `run_comparison.py` replays demand weighting and optionally recounts an
  explicitly supplied source archive with the repository's existing demand rules.
- `fixtures/frozen_scores.json` contains anonymous numeric assessments only.
  Cases 01-03 are historical test fixtures for the three job families. Cases
  04-06 are three historical outputs for the same confirmed AI Engineer resume,
  not three independent applicants. No original resume text is included.
- `results.json` contains the three aggregate demand snapshots, exact historical
  case comparisons, cohort counts, selected demand changes and source fingerprints.
  Private paths, job IDs, raw qualifications, names and model responses are omitted.
- `test_scope.py` checks replay, scope boundaries and unchanged score fields.

The recorded original recount took 31.603 seconds and made zero new Agent calls.
That historical duration is not the duration of the packaged aggregate replay.

## Run locally

From the repository root, using Python 3.10 or later:

```powershell
python backend/experiments/entry_level_skill_gaps/job_scope/run_comparison.py
python -m unittest discover -s backend/experiments/entry_level_skill_gaps/job_scope -p test_scope.py -v
```

The default run uses only the committed aggregate counts and anonymous scores.
It reproduces the 18 historical case/cohort comparisons without requiring login
credentials, the original source archive or application environment variables.

To recount a separately supplied archive instead:

```powershell
python backend/experiments/entry_level_skill_gaps/job_scope/run_comparison.py --source-zip "source.zip"
```

The archive must contain `job_postings_analyses.json` and
`job_analysis_qualifications.json` in the format expected by
`backend/scripts/demand_snapshot.py`. The archive is not distributed here. If it
matches the historical source fingerprint, the script rejects count drift. A
different source is identified as a new comparison, not a replay of the saved
historical results. No archive is extracted to disk.

An optional `--output <new-report.json>` writes a new report and refuses to
overwrite an existing file. Without that option, the command writes no files.

## Historical results

| Case | Family | All levels | Entry only | Entry plus intern |
| --- | --- | ---: | ---: | ---: |
| case_01 | Software Engineer | 41.53% | 41.94% | 41.64% |
| case_02 | AI Engineer | 33.70% | 33.21% | 34.93% |
| case_03 | Data Analyst | 55.49% | 50.00% | 57.76% |
| case_04 | AI Engineer | 48.44% | 47.50% | 46.38% |
| case_05 | AI Engineer | 46.27% | 43.46% | 45.64% |
| case_06 | AI Engineer | 41.34% | 41.54% | 39.79% |

All individual evidence scores, gaps, grades and pending states remain unchanged.
Only demand weights, priorities and the resulting weighted match change. The
match excludes pending skills and skills with zero demand from its denominator.
The entry-only AI Engineer and Data Analyst samples are particularly small.

These are sensitivity examples, not evidence of improved scoring accuracy or
hiring probability. Original extraction uncertainty and errors remain present.
The packaged numeric replay does not validate the semantics of the original
Agent assessments or prove that the underlying seniority labels are correct.
