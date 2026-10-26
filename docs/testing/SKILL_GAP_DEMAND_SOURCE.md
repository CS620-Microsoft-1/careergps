# Skill Gap demand snapshot: source and reproduction

The application currently reads a **fixed export snapshot**, not a live SQL
aggregate. This PR keeps its counts and ratios unchanged. The snapshot is not
presented as a verified sample of postings from the last 90 days.

## Published snapshot

| Field | Value |
| --- | --- |
| Analysis version | `careergps-compact-core-v3.0` |
| Original calculation time | `2026-10-24T18:35:44.029431Z` |
| Software Engineer | N = 2,858; 22 core skills |
| Data Analyst | N = 174; 18 core skills |
| AI Engineer | N = 566; 23 core skills |
| Source parent rows | 3,715 |
| Source qualification rows | 38,065 |
| Included parent postings | 3,598 |
| Excluded unclassified parent postings | 117 (`job_family: null`) |
| Original six-table ZIP SHA-256 | `bfb06458c984b5fd7f76e892af95eb68ab373a9fa63fec7f81150695795fa9cd` |
| Original aggregate SHA-256 | `d47b1bafc91c7f0ae98ff5cf0c5f3f2f85f1c848ab03455de56b4bc34e7546ab` |
| Original analysis fingerprint | `8766af4a81703dc686566d8a316e18f9e184c704a73e7da3d732b57a76eadf44` |

The original input was a team-supplied `six_tables_split.zip`. Its schema resembles
the job-analysis tables, but the export alone does not establish that it was
produced by PR #20 or exported from the production database. The source export and
historical outputs are not committed to this repository.

The original calculation time is a **computation timestamp**, not a posting date
range. The two tables used here do not provide enough information to verify
`first_seen_at`, a 90/180-day window, company coverage, US geography, or cross-board
duplicate postings. All supplied seniorities are included. Postings are deduplicated
by their supplied `job_posting_id`; distinct IDs are not assumed to be distinct
real-world vacancies.

## Inputs and counting rules

Only two of the six tables affect the calculation:

1. `job_postings_analyses.json`: supplies each `job_posting_id` and its existing
   `job_family`. The tool does not classify job titles again.
2. `job_analysis_qualifications.json`: joined by `job_posting_id`; uses `value`,
   `level`, `position`, `categories`, and preserves `evidence` for audit.

The frozen deterministic rules recognize fine requirements, retain ambiguous or
conditional clauses for review, and project supported requirements into the fixed
22/18/23 core-skill catalog. No LLM is used. The parser is a retained rule system,
not a claim that every natural-language requirement is correctly understood.
The status remains `computed_with_review_queue`.

For each core skill and each posting, repeated mentions count once. If a posting
has multiple qualifying levels, precedence is `required > preferred > unspecified`.
Thus `preferred_only` excludes a posting already counted as required. Unresolved
or conditional options are retained separately and are not relabeled unspecified.

```text
N = all parent postings assigned to this job family
required_ratio       = required_job_count / N
preferred_only_ratio = preferred_only_job_count / N
unspecified_ratio    = unspecified_job_count / N
```

Ratios are rounded to six decimal places. A posting with no qualifications remains
in N. Null-family postings are excluded, and duplicate parent IDs, unknown families,
foreign qualification references, and unsupported levels are rejected.

The parser and mappings are committed under `backend/scripts/demand_rules/`:

- `fine.py`: the frozen fine-criterion aliases, context guards, and clause parsing.
- `compact.py`: the frozen projection and posting-level aggregation rules.
- `taxonomy.py`: the fine-to-core/module mappings, with English display names.
- `base_catalog.json`: the base recognition patterns.

These are the necessary retained calculation rules, without historical test runs,
personal resume inputs, machine-specific paths, or old experiment entry points.
Changing display names or relocating imports does not change their matching
patterns or fine-to-core mappings.

## Reproduce from an export

Run from `backend` using its virtual environment. On Windows use
`.venv\Scripts\python.exe` in place of `python`; on macOS/Linux activate `.venv`
first. These commands have no database or network access.

```sh
python -m scripts.demand_snapshot replay \
  --source-zip /path/to/six_tables_split.zip \
  --output local_results/demand-replay \
  --verify-snapshot app/services/skill_gaps/data/market_snapshot.json
```

For separate JSON exports:

```sh
python -m scripts.demand_snapshot replay \
  --postings /path/to/job_postings_analyses.json \
  --qualifications /path/to/job_analysis_qualifications.json \
  --output local_results/demand-replay
```

The output directory must be new. Each family is checkpointed in batches, followed
by its `demand_ratio.json` and a combined `demand_analysis.json`. No runtime asset is
overwritten. `--verify-snapshot` compares all family denominators and all 63 core
skills' six count/ratio fields against the committed snapshot and fails on any
difference. A replay records current computation time, explicit input hashes, and
the portable rules' hashes; those provenance fields differ from the historical
analysis fingerprint, even when every count is identical.

The original team export was replayed locally with this portable tool: all three
N values and all 63 skills' counts and ratios matched the committed snapshot.

## Reproduce the snapshot export step

The historical compact analysis is converted into the runtime asset by copying
the existing count and ratio fields:

```sh
python -m scripts.demand_snapshot export \
  --analysis /path/to/demand_analysis.json \
  --output local_results/exported-market-snapshot.json
```

With the original aggregate identified by the SHA above, this produces the same
JSON object as the committed runtime asset, including its provenance fields.
`counts_recomputed: false` means **this export step copied already computed
statistics**. It does not mean the original qualification counts were never
calculated. Exporting a new replay preserves the new replay's provenance instead
of pretending to be the historical run.

## Tests and the later SQL transition

```sh
python -m unittest tests.test_skill_gap_demand -v
```

These tests create fictional table rows and temporary files. They verify
posting-level deduplication, level precedence, unspecified counts, no-qualification
denominators, null-family exclusion, invalid references, deterministic replay,
ZIP loading, export preservation, CLI checkpoints, and refusal to overwrite.
No ignored local export is needed to run them.

The later database implementation should join the stored postings and analyses,
apply ADR-003's `first_seen_at` window (90 days, or 180 with low confidence when
fewer than 30 postings qualify), and expose dates, company/source coverage, filters,
and immutable snapshot identity. SQL should calculate the final posting-level
counts and denominators after the same versioned normalization rules are applied.
That transition needs actual source metadata; this PR does not infer missing dates
or silently replace the current demand ratios.
