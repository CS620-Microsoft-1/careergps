# CareerGPS Skill Gap Analysis

For the current strict-schema, twenty-JD/three-resume experiment and setup on another computer, start with [Run locally](SKILL_GAP_RUN_LOCAL.md). The input example below documents the earlier raw-input v2 pipeline; it is retained for history and is not the new structured-JD contract.

This README describes the current inputs, scoring rules, and returned conclusions. The local example uses synthetic résumé and job-description content. Evidence scores, demand ratios, and gap scores are calculated from that content rather than supplied in the input files.

## 1. Résumé Information

The following is the complete current local input: the edited Review-page `ResumeClassification` object wrapped with `confirmed: true`. It contains original résumé content, without evidence scores or extracted evidence categories.

```json
{
  "confirmed": true,
  "classification": {
    "personal_information": {
      "name": "Alex Example",
      "emails": ["alex@example.test"],
      "phones": [],
      "location": "Madison, WI, United States",
      "linkedin": null,
      "github": null,
      "website": null
    },
    "research_interests": [],
    "education": [
      {
        "institution": "Example University",
        "degree": "Bachelor of Science",
        "major": "Computer Science",
        "start_date": "2022-09",
        "end_date": "2026-05",
        "gpa": null,
        "content": ["Coursework: algorithms, databases and SQL."]
      }
    ],
    "work_experience": [
      {
        "company": "Example Campus Lab",
        "title": "Student Software Developer",
        "start_date": "2025-06",
        "end_date": "2026-05",
        "location": "Madison, WI",
        "content": [
          "Used Git feature branches and pull requests to collaborate on a team application.",
          "Implemented Python scripts that transformed CSV data for the lab."
        ]
      }
    ],
    "research_experience": [],
    "projects": [
      {
        "name": "Campus Events API",
        "url": null,
        "technologies": ["Python", "FastAPI"],
        "content": [
          "Built a Python REST API using FastAPI to create and search campus events.",
          "Wrote and ran Python unit and integration tests covering API validation and error responses."
        ]
      },
      {
        "name": "Study Dashboard",
        "url": null,
        "technologies": ["JavaScript", "React"],
        "content": [
          "Implemented interactive React components and JavaScript filtering for a study dashboard."
        ]
      }
    ],
    "technical_skills": ["Python", "JS", "React.js", "Postgres", "Git", "SQL"],
    "languages": [{"name": "English", "proficiency": "Professional working proficiency"}],
    "publications": [],
    "awards_honors": [],
    "certifications": [],
    "leadership_activities": [],
    "other": [{"content": "Synthetic test résumé shaped like the current Review page output."}]
  }
}
```

## 2. Job Description Information

The current local input wraps the existing `NormalizedPosting` objects with company names in a `postings` array. The example below shows the outer format and the first complete record from the seven-record input. The full `description_text` is preserved; `\n` represents line breaks inside the JSON string. No skill counts, demand ratios, or extracted requirement labels are supplied.

```json
{
  "data_source": "synthetic",
  "postings": [
    {
      "company_name": "Example Northstar Labs",
      "posting": {
        "source": "greenhouse",
        "external_id": "demo-101",
        "title": "Software Engineer, New Grad - Backend",
        "location": "Madison, WI, United States",
        "country": "US",
        "workplace_type": "hybrid",
        "department": "Engineering",
        "employment_type": "full_time",
        "description_text": "About us\nExample Northstar Labs builds campus software. This is a synthetic job advertisement.\nResponsibilities\nBuild and maintain backend services with the team.\nRequired qualifications\nExperience building applications using Python.\nAbility to write queries and manage data using PostgreSQL.\nExperience collaborating with Git.\nPreferred qualifications\nExperience packaging an application with Docker.\nEligibility\nThis role is for new graduates and candidates with zero to two years of experience.",
        "salary_min": null,
        "salary_max": null,
        "salary_currency": null,
        "salary_interval": null,
        "url": "https://example.test/northstar/jobs/101",
        "published_at": "2026-10-01T12:00:00Z"
      }
    }
  ]
}
```

## 3. Résumé Evidence Score

The Agent classifies evidence; Python assigns the numerical score.

| Evidence | Score | Example |
|---|---:|---|
| No extracted supporting evidence | 0.00 | Docker is not mentioned |
| `listed` | 0.25 | PostgreSQL appears only in the skills list |
| `applied` | 0.60 | The résumé describes using Git branches and pull requests |
| `validated` | 0.80 | The résumé describes writing and running Python tests |
| Validated evidence in two different experience/project entries | 1.00 | The current rule treats two entries as corroborating evidence |

For each skill, Python normally takes the highest evidence score rather than adding scores together. For example, listed Python (0.25), applied Python (0.60), and validated Python (0.80) produce a final score of 0.80.

Current limitation: identical validation text copied into different entries can incorrectly trigger 1.00. Content-level deduplication is still needed.

These values are provisional evidence-coverage rules, not proficiency percentages. A zero means no evidence was extracted, not that the candidate lacks the skill. A testing statement in a résumé is not independently verified by this pipeline.

## 4. Job Demand Ratio

```text
Demand ratio = unique eligible postings requiring or preferring the skill
               / total eligible postings
```

Each posting counts at most once per skill, even if the skill appears repeatedly or is both required and preferred. Required and preferred-only counts are also recorded separately. Skills are normalized using configured aliases, such as JS → JavaScript and Postgres → PostgreSQL. Related skills such as SQL and PostgreSQL remain separate.

For Docker in the current sample:

```text
Required:        1 posting
Preferred only:  3 postings
Total eligible:  5 postings

Demand ratio = (1 + 3) / 5 = 0.80
```

The combined 80% is not an 80% mandatory requirement rate: only 20% explicitly require Docker. The current gap formula gives required and preferred mentions equal weight. Ratios across skills do not need to sum to 100%, because one posting can mention multiple skills.

## 5. Gap Score and Priority

```text
Gap score = demand ratio × (1 − résumé evidence score)
```

Python rounds the result to six decimal places and sorts skills by descending gap score.

| Priority | Rule |
|---|---|
| High | Gap score ≥ 0.60 |
| Medium | 0.30 ≤ gap score < 0.60 |
| Low | Gap score < 0.30 |

This is an experimental prioritization score for improving demonstrated evidence. It is not a skill-deficit percentage, job-match percentage, or hiring probability. The thresholds have not been calibrated against human-reviewed outcomes.

## 6. Returned Results and Conclusions

The latest successful run produced:

| Skill | Required postings | Preferred-only postings | Demand ratio | Evidence score | Gap score | Priority |
|---|---:|---:|---:|---:|---:|---|
| Docker | 1 | 3 | 80% | 0.00 | 0.80 | High |
| Git | 4 | 1 | 100% | 0.60 | 0.40 | Medium |
| PostgreSQL | 2 | 0 | 40% | 0.25 | 0.30 | Medium |
| SQL | 1 | 1 | 40% | 0.25 | 0.30 | Medium |
| JavaScript | 2 | 1 | 60% | 0.60 | 0.24 | Low |
| Python | 4 | 1 | 100% | 0.80 | 0.20 | Low |
| React | 1 | 0 | 20% | 0.60 | 0.08 | Low |

The final JSON returns:

- `target_role` and `seniority`: the selected career target.
- `confidence`: the sample-sufficiency flag; currently `low` because the sample has only five postings.
- `summary`: an overall explanation of the comparison.
- `strengths`: supported skills and explanations based on résumé evidence.
- `gaps`: each skill's `market_frequency`, `user_evidence_score`, `gap_score`, `priority`, `reason`, `recommended_action`, and `completion_evidence`.
- `limitations`: synthetic-data, sample-size, and scoring limitations.

Python verifies that the final Agent response preserves the calculated skills, order, numerical values, and priorities. Required/preferred counts and detailed evidence citations are saved in separate audit files; the current final-summary Agent input does not include the full count breakdown.

For this sample, the conclusion is that Python, JavaScript, React, and Git already have applied résumé evidence. Docker has no demonstrated evidence, while PostgreSQL and SQL have only listed/coursework evidence. A practical next step is to extend the existing FastAPI project with containerization and PostgreSQL/SQL functionality, then document the work. Git recommendations should strengthen genuine collaboration evidence rather than imply the candidate must learn Git from scratch.

These conclusions describe the fictional input documents and the current scoring rules. They do not establish a real candidate's ability or real market demand.
