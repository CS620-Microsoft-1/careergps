# Job posting analysis storage

Status: schema implemented for review; shared database migration and result persistence
are **not activated** by this change. The current API and worker continue to read source
postings through the protected read-only source and save analyses locally. The reserved
`save_analysis_to_supabase()` function still raises `SupabaseAnalysisPersistenceNotEnabled`.

## Ownership and tables

These are shared facts about a job, never a user's résumé, application or skill-gap result.
The storage shape follows the résumé schema's UUIDs, PostgreSQL JSONB/arrays, ordered child
rows, constraints and RLS. Unlike `resumes.confirmed_data`, no duplicate full output JSON
is stored: the six tables are the future canonical result. The parent has exactly **25
columns**: 28 output fields minus five child collections, plus one extra overview evidence
column, plus the backend-only `is_open` flag (28 - 5 + 1 + 1 = 25).

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
Closing a posting only sets the source's `closed_at`; it does not delete an analysis
or synchronize the temporary `is_open` flag yet.

## Complete mapping from the current 28-field output

| Agent field(s) | Destination |
| --- | --- |
| `id` | `job_postings_analyses.job_posting_id` (UUID; no new ID generated) |
| `source`, `external_id`, `company_slug`, `company_name`, `company_tier`, `job_title`, `job_family`, `seniority`, `department`, `benefits`, `salary_currency`, `salary_interval`, `url` | Same-named nullable `TEXT` columns on the parent |
| `published_at`, `first_seen_at`, `last_seen_at`, `closed_at` | Same-named nullable `TIMESTAMPTZ` columns on the parent |
| `content_hash` | Parent `source_content_hash` |
| `created_at`, `updated_at` | Parent `source_created_at`, `source_updated_at` |
| `role_overview.value`, `role_overview.evidence` | Parent `role_overview TEXT`, `role_overview_evidence JSONB` |
| `other_relevant_information` | Parent `TEXT[]`; `[]` means no supplemental facts |
| `locations[]` | Location rows with `value`, `evidence`, and array `position` |
| `responsibilities[]` | Responsibility rows with `value`, `evidence`, and array `position` |
| `qualifications[]` | Qualification rows with `value`, `level`, `categories TEXT[]`, `evidence`, `position` |
| `job_conditions[]` | Condition rows with `type`, `value`, `evidence`, `position` |
| `compensation[]` | Compensation rows with `type`, `value`, `minimum NUMERIC`, `maximum NUMERIC`, `currency`, `interval`, `applies_to`, `evidence`, `position` |

Empty arrays create zero detail rows. Unknown scalar values stay SQL NULL; a null role
overview has empty evidence. Evidence remains a JSON array of `{source_field, quote}`
objects. No evidence table is needed. Do not flatten an AND/OR requirement into several
mandatory rows or convert team technologies into candidate requirements. Category tags
may overlap; they do not create duplicate requirement rows. `benefits` is a string/null,
and other relevant information is a string array, matching the active output format.

No invented country/city columns, skill-normalization layer, or per-user fields are added.
Locations such as `SF` remain source-supported text. Classifying an item as a sponsorship
condition does not by itself mean that the employer offers sponsorship.

The only additional parent field is `is_open BOOLEAN NOT NULL`, with Python and database
insert defaults of `true`. It is a temporary backend placeholder: all newly stored analyses
are treated as open, even when the copied `closed_at` is non-null. It is not an Agent output
field, verified availability, or an analysis-success status. There is no constraint coupling
it to `closed_at` yet. Future backend synchronization should derive it from the current
`job_postings.closed_at` without calling the Agent again. Explicit false values remain
representable for that future work; no availability synchronization is activated now.

The seven management columns (`source_snapshot`, `agent_name`, `agent_version`,
`schema_version`, `analyzed_at`, `created_at`, `updated_at`) are intentionally omitted.
The original posting times are still stored as `source_created_at` / `source_updated_at`;
they do not represent analysis or storage times. TIMESTAMPTZ preserves their instant,
not the original string formatting. Source metadata describes the input at analysis time,
not necessarily the current source record. Evidence quotes and `source_content_hash` remain,
but the complete historical input, analysis versions, and analysis timestamps cannot be
recovered from these six tables. This is the accepted minimal-storage tradeoff.

## Queries and constraints

The parent has a B-tree index on `(job_family, seniority)`. These are direct scalar columns,
not generated JSON projections. Unknown levels remain NULL; `multiple_levels` is not
expanded into guesses. To find AI internship analyses under the temporary open-state assumption:

```sql
SELECT a.job_posting_id, a.job_title, a.company_name
FROM job_postings_analyses AS a
WHERE a.is_open IS TRUE
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
after review and merge. No application import or startup runs migrations. Downgrade drops
the five children before the parent and destroys these analysis results; it does not drop
source postings or résumé tables.

Offline checks from `backend/` (no real database URL or Azure login needed):

```text
python -c "import os, unittest; os.environ.update(DATABASE_URL='postgresql+psycopg://tester:not-a-real-password@127.0.0.1:1/test', JOB_ANALYSIS_PROJECT_ENDPOINT='', JOB_ANALYSIS_ADMIN_TOKEN='', FOUNDRY_PROJECT_ENDPOINT='', FOUNDRY_AGENT_NAME=''); unittest.main(module=None, argv=['unittest', 'discover', '-s', 'tests', '-t', '.', '-v'])"
```

`test_job_posting_analysis_schema.py` compares the active output contract with model fields,
checks enum alignment and identity, and renders PostgreSQL upgrade/downgrade SQL in memory.
It compares migration columns, constraints, defaults, indexes and FKs against ORM metadata,
checks RLS statements, the exact 25-column parent and true open-state defaults, and never
connects to PostgreSQL. Existing pipeline tests continue
to verify that the reserved cloud writer is disabled. Offline DDL compilation does not
replace executing integrity/RLS tests against a disposable PostgreSQL database before rollout.
