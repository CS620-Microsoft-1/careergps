# ADR-003: Career Market Data Sources

- **Status:** Pending Approval
- **Date:** 2026-10-13
- **Decision Owners:** CareerGPS Development Team
- **Project:** CareerGPS
- **Scope:** Where the Market Intelligence feature gets job-market data, and how that data is turned into statistics

---

## 1. Context

The Market Intelligence Agent tells a student what employers currently ask for in a target role: the most requested skills, salary ranges, how demand is changing, and whether employers sponsor work visas.

Those answers must be accurate and explainable. A student should be able to see how many postings a number came from, over what period, and open example postings that support it.

---

## 2. Decision

CareerGPS will collect job postings from the public job-board APIs of three applicant tracking systems:

| Source     | Endpoint                                                          | Notes                                        |
| ---------- | ----------------------------------------------------------------- | -------------------------------------------- |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`     | Full description as escaped HTML             |
| Ashby      | `api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | Plain-text description and salary ranges |
| Lever      | `api.lever.co/v0/postings/{slug}?mode=json`                       | Plain-text description, country, workplace type |

All three are public, require no credentials, and return the full posting text.

Postings are ingested daily into the relational database. Statistics such as skill frequency, salary percentiles and trends are computed with SQL over the stored postings. LLMs are used only where they are reliable and testable: extracting structured fields from a single posting, and explaining statistics that were already computed. An LLM never produces a statistic.

### Scope rules

- **Companies:** a curated list in `backend/data/companies.yaml`, prioritizing large, well-known employers that students apply to.
- **Location:** United States postings and remote postings open to the United States.
- **Window:** statistics use postings first seen in the last 90 days. When a role has fewer than 30 postings in that window, the window widens to 180 days and the result is labeled low confidence.
- **History:** these APIs only return currently open postings. History therefore begins on the first day of ingestion, and ingestion should run daily from the start.

### Visa sponsorship

The job-board APIs have no sponsorship field. Sponsorship will be combined from two signals:

1. Statements in the posting text, such as "will not sponsor" or "U.S. citizenship required".
2. Employer-level history from public U.S. government data: the USCIS H-1B Employer Data Hub and the Department of Labor LCA disclosure data.

The product will present these as signals the student should verify with the employer, never as guarantees.

---

## 3. Alternatives Considered

### 3.1 LLM web search at request time

An agent with web grounding reads a handful of pages per query, often articles rather than postings. Its percentages are not computed from data, two runs can disagree, and there is no sample size or date range to show. **Rejected** as the primary source. It may be reconsidered as a labeled fallback for rare roles.

### 3.2 Adzuna API

Adzuna aggregates postings from many employers, including large companies outside these three platforms. It returns only a truncated description, which usually omits the requirements section, and its free tier is rate limited. **Rejected** because it does not provide the text needed for skill and sponsorship extraction.

### 3.3 Scraping LinkedIn, Indeed or company career sites

These sites prohibit automated collection in their terms and actively block it. **Rejected.**

### 3.4 Licensed labor-market data (for example, Lightcast)

The most complete option, but paid. **Deferred** unless the project sponsor or the university provides access.

---

## 4. Consequences

### Positive

- Every statistic is computed from stored postings and can cite them.
- Full posting text supports accurate skill and sponsorship extraction.
- No credentials are needed for collection.

### Negative

- **Coverage bias.** Most of the largest technology companies and most Fortune 500 companies use their own career sites or Workday, so they are not covered. The UI must state coverage, for example "based on N postings from M companies".
- **Per-company lists.** These APIs have no cross-company search, so the company list must be curated and maintained.
- **No backfill.** Trends become meaningful only after several weeks of daily ingestion.

### Usage and terms

The APIs exist so that companies can display their own openings. CareerGPS will request each board at most once per day, wait between requests, store postings for aggregate analysis, and link to the original posting instead of republishing full descriptions.

---

## 5. Future Considerations

- A Workday adapter to cover more Fortune 500 employers, subject to a terms review.
- O\*NET occupation codes for role normalization.
- Azure AI Search over stored postings for retrieval and evidence.
