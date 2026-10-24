# Job posting analysis storage

Status: schema implemented for review; shared database migration and result persistence
are **not activated** by this change. The current API and worker continue to read source
postings through the protected read-only source and save analyses locally. The reserved
`save_analysis_to_supabase()` function still raises `SupabaseAnalysisPersistenceNotEnabled`.

## Ownership and tables

These are shared facts about a job, never a user's résumé, application or skill-gap result.
The storage shape follows the résumé schema's UUIDs, PostgreSQL JSONB/arrays, ordered child
rows, constraints and RLS. The Agent v13 output remains exactly **28 fields**; its schema,
validation, API response and complete local JSON exports are unchanged. Relational storage
is a selected projection, not a lossless copy of that JSON. It uses exactly **10 parent
columns** and five child tables; source metadata is read by joining `job_postings`.

| Table | One row represents | Link |
| --- | --- | --- |
| `job_postings_analyses` | The current successful analysis of an existing posting | `job_posting_id` is both PK and FK to `job_postings.id` |
| `job_analysis_locations` | One explicit work-location entity | FK `job_posting_id` to the analysis |
| `job_analysis_responsibilities` | One logically complete responsibility | Same |
| `job_analysis_qualifications` | One logically complete job requirement, including alternatives | Same |
| `job_analysis_conditions` | One employment/eligibility condition with its exceptions | Same |
| `job_analysis_compensation` | One compensation type and applicable scope | Same |

Each child has an independent UUID `id`, `job_posting_id`, zero-based `position`, full
`value TEXT` and `evidence JSONB`. `(job_posting_id, position)` is unique within each child
table; its index also serves ordered per-job reads. Five requirements for one job share
the same `job_posting_id` but have distinct child IDs. No parent column stores lists of
child IDs. Foreign keys cascade physical deletion from source to analysis to details.
Closing a posting only sets the source's `closed_at`; it does not delete an analysis.
There is no `is_open` column or availability synchronization job. Queries use the current
source's `closed_at IS NULL` (the ingestion system's recorded state, not a fresh live-site check).

## Parent columns

| Column | PostgreSQL type | Meaning |
| --- | --- | --- |
| `job_posting_id` | `UUID PRIMARY KEY` | Also FK to `job_postings.id`; never generate a second job identity |
| `job_family` | nullable `TEXT` | Agent-derived occupational family |
| `seniority` | nullable `TEXT` | Agent-derived seniority |
| `role_overview` | nullable `TEXT` | Agent-derived overview value |
| `role_overview_evidence` | `JSONB NOT NULL`, default `[]` | Overview evidence; empty only when overview is null |
| `benefits` | nullable `TEXT` | Agent-derived benefits string |
| `other_relevant_information` | `TEXT[] NOT NULL`, default empty array | Supplemental facts |
| `source_content_hash` | nullable `TEXT` | Hash copied from the input used for this analysis |
| `agent_version` | `TEXT NOT NULL` | Actual Agent version used, e.g. `13`, supplied by backend |
| `analyzed_at` | `TIMESTAMPTZ NOT NULL` | Time this successful analysis completed, supplied by backend |

`agent_version` and `analyzed_at` have no insert defaults. A future writer must provide
provenance from the successful run, not the current application version or import time.
They do not belong in the Agent's 28-field output. The current local queue/exports have
no per-result analysis timestamp, so historical files cannot be silently backfilled using
an invented `analyzed_at`. Add trusted local run metadata or perform a fresh analysis when
implementing persistence. This schema change does not migrate or enrich local exports.

Keep `source_content_hash` as the analyzed input's hash, even if the source changes later.
Compare it with the current `job_postings.content_hash` to detect stale results. A null hash
means freshness cannot be established. The hash is not a historical source snapshot.

## Mapping from the unchanged 28-field output

| Agent field(s) | Relational destination / read policy |
| --- | --- |
| `id` | Parent `job_posting_id` |
| `source`, `external_id`, `company_slug`, `company_tier`, `url` | Not copied; read current same-named columns from `job_postings` |
| `published_at`, `first_seen_at`, `last_seen_at`, `closed_at`, `created_at`, `updated_at` | Not copied; read current source timestamps |
| `content_hash` | Parent `source_content_hash`, preserving which input was analyzed |
| `company_name`, `job_title`, `department` | Not persisted from Agent; read source `company_name`, `title`, `department` |
| `salary_currency`, `salary_interval` | No parent summary columns; use analysis compensation rows for extracted pay facts, or source columns explicitly for source-reported summaries |
| `job_family`, `seniority`, `benefits` | Same-named nullable parent columns |
| `role_overview.value`, `role_overview.evidence` | Parent `role_overview`, `role_overview_evidence` |
| `other_relevant_information` | Parent `TEXT[]`; `[]` means no supplemental facts |
| `locations[]` | `job_analysis_locations`: `id`, `job_posting_id`, `position`, `value`, `evidence` |
| `responsibilities[]` | `job_analysis_responsibilities`: `id`, `job_posting_id`, `position`, `value`, `evidence` |
| `qualifications[]` | `job_analysis_qualifications`: common five columns plus `level TEXT`, `categories TEXT[]` |
| `job_conditions[]` | `job_analysis_conditions`: common five columns plus `type TEXT` |
| `compensation[]` | `job_analysis_compensation`: common five columns plus `type TEXT`, `minimum NUMERIC`, `maximum NUMERIC`, `currency TEXT`, `interval TEXT`, `applies_to TEXT` |

All common child columns are non-null: `id UUID` is the PK, `job_posting_id UUID` the FK,
`position INTEGER` the zero-based array order, `value TEXT` the complete item, and
`evidence JSONB` its supporting quotes. Qualification `level`/`categories` and condition/
compensation `type` are required. Compensation bounds, currency, interval and applies_to
are nullable. The five child tables have 5, 5, 7, 6 and 11 columns respectively.

Empty arrays create zero detail rows. Unknown scalar values stay SQL NULL; a null role
overview has empty evidence. Evidence remains an array of `{source_field, quote}` objects.
Do not flatten an AND/OR requirement into several mandatory rows or convert team technologies
into candidate requirements. Category tags may overlap without creating duplicate rows.

### Decision on the five potentially overlapping fields

These five fields are **not** in `COPIED_METADATA_FIELDS`; do not claim the validator proves
them identical to the source. Their v13 definitions were reviewed individually:

| Field | Agent semantics | Storage decision and cost |
| --- | --- | --- |
| `company_name` | Explicit input company, potentially supplemented from description; no invented conflict resolution | Use source identity. The current source column is required. Agent-only supplementation or conflict-related nulls remain in local JSON, not this projection. |
| `job_title` | Normally input `title`, preserving wording and specialization; not a normalized occupational label | Use source `title`; `job_family` is the separate normalized filter. Any Agent-selected alternative title remains only in local JSON. |
| `department` | Explicit department or team, potentially extracted from description even when source department is null | Use source `department`. This deliberately forgoes Agent-only department enrichment in relational storage; no current analysis filter requires it. |
| `salary_currency` | Common explicitly supported currency across all relevant base salary/hourly arrangements | Keep each compensation item's currency and scope; omit the redundant summary column. Do not substitute source salary currency and call it Agent-derived. |
| `salary_interval` | Common normalized period across all relevant base salary/hourly arrangements | Keep each compensation item's period and scope; omit the summary column. No annualization or inferred period. |

A consumer needing a pay summary should consider **all** relevant `base_salary`/`hourly_rate`
rows and return unknown if no relevant rows exist, any value is unknown, values differ, or
applicability is unresolved. Selecting the first row is incorrect. Such a derived summary
is not guaranteed to reproduce the Agent's original null/non-null decision. Exact output
replay uses the unchanged local JSON; these six tables do not provide that guarantee.

No `source_created_at`, `source_updated_at`, analysis `created_at`/`updated_at`,
`source_snapshot`, `agent_name` or `schema_version` is stored. Provenance is the actual
Agent version, analysis completion time and analyzed content hash. A join returns **current**
source data, not the historical input. Old source text, original source metadata and prior
analysis versions cannot be reconstructed from this schema. If historical evidence must
remain independently verifiable after source edits, a future snapshot/history design is needed.

No invented country/city columns, skill-normalization layer or per-user fields are added.
Locations such as `SF` remain source-supported text. A sponsorship condition does not by
itself mean that the employer offers sponsorship.

## Queries and constraints

The parent has a B-tree index on `(job_family, seniority)`. These are direct scalar columns,
not generated JSON projections. Unknown levels remain NULL; `multiple_levels` is not
expanded into guesses. To find AI internship analyses for postings currently recorded as open:

```sql
SELECT a.job_posting_id, p.title, p.company_name, a.agent_version, a.analyzed_at
FROM job_postings_analyses AS a
JOIN job_postings AS p ON p.id = a.job_posting_id
WHERE p.closed_at IS NULL
  AND a.job_family = 'ai_engineer'
  AND a.seniority = 'intern';
```

To read one job's required skill-related requirements (bind `:job_id` in SQLAlchemy):

```sql
SELECT id, position, value, level, categories, evidence
FROM job_analysis_qualifications
WHERE job_posting_id = :job_id
  AND level = 'required'
  AND 'skill' = ANY(categories)
ORDER BY position;
```

To read one requirement directly, query its primary key `id`. This alone does not decide
whether a user meets it; the downstream skill-gap agent still interprets the complete
requirement, alternatives, evidence and résumé. Add further indexes only when needed by
actual query plans; no broad JSONB or category GIN indexes are added in this schema change.

Database constraints cover the parent/source foreign key, allowed enums, unique per-job positions,
nonnegative positions, nonblank detail values, nonempty JSON evidence arrays, nonempty
one-dimensional allowed category arrays without NULL elements, nonnegative finite money,
and lower/upper amount ordering. NULL monetary bounds/currency/period remain valid.
NUMERIC has no imposed rounding scale. There is no inferred currency or annualization.

The existing application validators must still run before persistence: they check the
full JSON shape, evidence object keys and exact source quotes, duplicate categories,
blank values, copied metadata and cross-field consistency. SQL CHECKs are not a replacement
for those validators and do not prove semantic support or extraction completeness.

## Future persistence boundary

Implementing a writer, read endpoints and cross-machine task ownership is a separate step.
The intended writer validates first, then inserts the parent and all children in one
transaction. Existing successful results are skipped by default; the parent PK prevents
duplicate result rows. Only an explicitly requested successful refresh replaces the parent
values and rebuilds all details in one transaction. A failed refresh preserves the old result.

Child IDs identify the current analysis items, not stable requirements across replacements.
Future persisted skill-gap results must keep enough analysis provenance/content to avoid
silently associating old conclusions with replacement rows. No analysis history is added.
The result-table PK does not prevent concurrent workers making duplicate Agent calls;
shared claiming/leases must be implemented before enabling a multi-machine writer.

Locally generated job UUIDs in exported fixtures may not exist in `job_postings`. Do not
disable the FK or silently insert/reassign source postings to import those files.

## Migration, access and verification

Migration `7d2c91a4e8b6` follows résumé revision `02a858fed0df`. It creates only these six
tables and the parent search index, and enables RLS on all six. It does not backfill data,
change original job rows, add broad access grants/policies, or call any service. The current
architecture uses backend SQLAlchemy connections with the Supabase Data API disabled;
ordinary clients receive no direct access from this migration. Shared authenticated reads
and restricted writes must be enforced by the future backend endpoints/DB roles.

As with résumé #17, only the database owner applies the migration to the shared database
after review and merge. Revision `7d2c91a4e8b6` is amended in place because it has not been
applied to the shared database; an already-applied database would require a new migration.
No application import or startup runs migrations. Downgrade drops
the five children before the parent and destroys these analysis results; it does not drop
source postings or résumé tables.

Offline checks from `backend/` (no real database URL or Azure login needed):

```text
python -c "import os, unittest; os.environ.update(DATABASE_URL='postgresql+psycopg://tester:not-a-real-password@127.0.0.1:1/test', JOB_ANALYSIS_PROJECT_ENDPOINT='', JOB_ANALYSIS_ADMIN_TOKEN='', FOUNDRY_PROJECT_ENDPOINT='', FOUNDRY_AGENT_NAME=''); unittest.main(module=None, argv=['unittest', 'discover', '-s', 'tests', '-t', '.', '-v'])"
```

`test_job_posting_analysis_schema.py` compares the active output contract with model fields,
checks enum alignment and identity, and renders PostgreSQL upgrade/downgrade SQL in memory.
It compares migration columns, constraints, defaults, indexes and FKs against ORM metadata,
checks RLS statements, the exact 10-column parent, required provenance, source joins and absence
of copied metadata/`is_open`, and never connects to PostgreSQL. Existing pipeline tests continue
to verify that the reserved cloud writer is disabled. Offline DDL compilation does not
replace executing integrity/RLS tests against a disposable PostgreSQL database before rollout.

An optional embedded PostgreSQL check is also available. From the repository root, with
Node.js, a Python environment containing the backend requirements, and an externally
installed `@electric-sql/pglite` package:

```text
node backend/tests/check_job_posting_analysis_postgres.mjs /path/to/python /path/to/node_modules/@electric-sql/pglite
```

The script renders the current migration chain offline, bypasses application configuration,
and executes it in an in-memory PGlite engine with synthetic source data. It verifies required
provenance, constraints, all five cascades, source JOIN/closure/hash behavior, RLS with a
non-superuser role, downgrade and re-upgrade. It does not load `.env`, connect to Supabase,
or validate hosted Supabase roles/configuration. The script does not install dependencies;
PGlite is optional and is not needed for the Python offline suite.
