"""Turn real GitHub sources (data/project_sources.yaml) into project-catalog entries.

Two kinds of source:
  * idea_list: a repo whose README lists project ideas in Markdown tables
    (e.g. The-Cool-Coders/Project-Ideas-And-Resources).
  * topic: a GitHub topic (e.g. open-source-projects); its top repos become
    "contribute to <repo>" projects.

Every entry has the same shape as data/projects.json, so the resources agent, the rule
ranking and the Resources page use them unchanged. Skills come only from conservative
keyword rules over the name, description, language and topics: a project is only offered for
a role when it practices at least one skill specific to that role.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable

import httpx2

from app.services.skill_gaps.assets import ASSET_ROOT

GITHUB_API = "https://api.github.com"
RAW_GITHUB = "https://raw.githubusercontent.com"
USER_AGENT = "CareerGPS/0.1 (project catalog sync; +https://github.com/CS620-Microsoft-1/careergps)"

# Same career_path names as data/projects.json (see FAMILY_TO_CATALOG in resources.py).
CAREER_PATHS = {
    "software_engineer": "Software Engineering",
    "data_analyst": "Data Analyst",
    "ai_engineer": "AI/ML Engineering",
}
_FAMILY_PREFIX = {"software_engineer": "swe", "data_analyst": "data", "ai_engineer": "aiml"}

# (pattern, skill ids). Patterns are matched case-insensitively on word boundaries against
# "name. description. language. topics".
_SWE_RULES: list[tuple[str, tuple[str, ...]]] = [
    (r"react(?:\s?js)?|vue|angular|svelte|next\.?js|html|css|tailwind|front[- ]?end|user interfaces?|\bui\b|clone", ("frontend",)),
    (r"rest(?:ful)? api|graphql|express|django|flask|fastapi|spring(?: boot)?|node(?:\.?js)?|back[- ]?end|\bapi\b|server", ("backend_apis",)),
    (r"full[- ]?stack|mern|mean stack", ("frontend", "backend_apis")),
    (r"mern|mongo(?:db)?|firebase|firestore|redis|elasticsearch|harperdb|nosql", ("nosql_search",)),
    (r"sql|postgres(?:ql)?|mysql|sqlite|relational database", ("relational_sql",)),
    (r"websockets?|real[- ]time|micro[- ]?services?|distributed|kafka|multiple users", ("distributed_systems",)),
    (r"docker|kubernetes|k8s|containers?", ("containers",)),
    (r"aws|azure|gcp|google cloud|cloud|serverless|vercel|netlify", ("cloud",)),
    (r"auth(?:entication|orization)?|nextauth|oauth|jwt|password|security|encryption", ("security",)),
    (r"tests?|testing|jest|pytest|cypress|unit tests?", ("testing",)),
    (r"ci/cd|github actions|continuous integration|devops", ("delivery_automation",)),
    (r"algorithms?|chess|tic[- ]tac[- ]toe|sudoku|path ?finding|data structures", ("algorithms",)),
    (r"monitoring|observability|logging|prometheus|grafana", ("observability_operations",)),
]
_DATA_RULES: list[tuple[str, tuple[str, ...]]] = [
    (r"sql|postgres(?:ql)?|mysql|sqlite|bigquery|duckdb", ("sql",)),
    (r"pandas|jupyter|notebooks?|numpy|\br\b|data analysis|analytics|exploratory", ("analytical_scripting", "data_analysis")),
    (r"visuali[sz]ation|charts?|plotly|matplotlib|seaborn|d3(?:\.js)?|dashboards?", ("data_visualization",)),
    (r"dashboards?|streamlit|power ?bi|tableau|looker|metabase|superset", ("dashboarding",)),
    (r"power ?bi|tableau|looker|metabase|superset", ("bi_tools",)),
    (r"statistics|statistical|regression|hypothesis", ("statistics",)),
    (r"a/?b test(?:ing)?|experiment analysis", ("experimentation",)),
    (r"etl|elt|airflow|dagster|prefect|data pipelines?|ingestion|scrap(?:er|ing)", ("data_pipelines",)),
    (r"dbt|data model(?:ing)?|star schema|warehouse|snowflake|redshift", ("data_modeling", "warehousing")),
    (r"spark|pyspark|hadoop|big data", ("large_scale_processing",)),
    (r"data cleaning|data quality|great expectations|data validation", ("data_quality",)),
    (r"excel|spreadsheets?|google sheets", ("spreadsheets",)),
]
_AI_RULES: list[tuple[str, tuple[str, ...]]] = [
    (r"machine learning|\bml\b|scikit[- ]learn|sklearn|recommend(?:ation|er)?|fraud detection|classifier|classification|prediction|predictive", ("machine_learning", "model_training")),
    (r"deep learning|neural net(?:work)?s?|pytorch|tensorflow|keras|cnn|transformers?|opencv|computer vision|face recognition|image recognition", ("deep_learning",)),
    (r"fine[- ]?tun(?:e|ing)|lora", ("fine_tuning",)),
    (r"llms?|gpt|openai|large language models?|chatgpt|gemini|claude|llama|ollama", ("llm", "generative_ai")),
    (r"generative ai|gen ?ai|stable diffusion|diffusion", ("generative_ai",)),
    (r"rag|retrieval[- ]augmented(?: generation)?", ("rag",)),
    (r"embeddings?|vector (?:db|database|search|store)|pinecone|faiss|chroma|weaviate|qdrant", ("vector_retrieval",)),
    (r"ai agents?|agentic|langchain|langgraph|autogen|crewai|tool use|function calling", ("ai_agents",)),
    (r"prompt engineering|prompt templates?|system prompts?", ("prompt_engineering",)),
    (r"mlops|mlflow|kubeflow|model registry|weights (?:&|and) biases", ("mlops",)),
    (r"model serving|inference server|deploy(?:ed|ment)? (?:a |the )?model", ("model_deployment",)),
    (r"model evaluation|llm evals?|evals? (?:harness|framework)", ("model_evaluation",)),
    (r"feature engineering", ("feature_engineering",)),
]

_RULES = {"software_engineer": _SWE_RULES, "data_analyst": _DATA_RULES, "ai_engineer": _AI_RULES}
# Skills every entry gets in a role it qualifies for (it is code in a GitHub repository).
_BASE_SKILLS = {
    "software_engineer": ("programming", "version_control"),
    "data_analyst": (),
    "ai_engineer": (),
}
_LANGUAGE_SKILLS = {
    "ai_engineer": {"python": ("python",)},
    "data_analyst": {"python": ("analytical_scripting",), "r": ("analytical_scripting",),
                     "jupyter notebook": ("analytical_scripting",)},
}
# A role needs at least one of its own skills, not just these generic ones.
_GENERIC = {"programming", "version_control", "python", "analytical_scripting"}

_LIST_REPO = re.compile(
    r"awesome|curated|\blist of\b|collection of|roadmaps?|interview|cheat ?sheets?|resources|"
    r"tutorials?|books?|hacktoberfest|first[- ]contributions?|project[- ]ideas|for beginners",
    re.I,
)

_TIERS = {
    "1": ("beginner", 15),
    "2": ("intermediate", 30),
    "3": ("advanced", 50),
}
MAX_DESCRIPTION = 280


@dataclass
class RawProject:
    """One project before skills are assigned."""

    source_id: str
    slug: str
    title: str
    description: str
    url: str
    difficulty: str
    estimated_hours: int
    kind: str  # "idea" or "open_source"
    language: str | None = None
    topics: list[str] = field(default_factory=list)
    stars: int | None = None


# --- Parsing -------------------------------------------------------------------------------------

_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _clean(text: str, limit: int = MAX_DESCRIPTION) -> str:
    """Untrusted text from GitHub: strip Markdown/HTML noise and cap length before it reaches the agent."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[`*_#>]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def parse_idea_table(markdown: str, source_id: str) -> list[RawProject]:
    """Rows shaped `| [Name](url) | Short description | 1-Beginner |` from any Markdown table."""
    projects: list[RawProject] = []
    seen: set[str] = set()
    for line in markdown.splitlines():
        row = _ROW.match(line)
        if not row:
            continue
        cells = [cell.strip() for cell in row.group(1).split("|")]
        if len(cells) < 3:
            continue
        link = _LINK.search(cells[0])
        tier = re.match(r"\s*(\d)", cells[2])
        if not link or not tier:
            continue  # header, separator, or a non-project table (e.g. tutorials)
        title = _clean(link.group(1), 80)
        slug = slugify(title)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        difficulty, hours = _TIERS.get(tier.group(1), ("intermediate", 30))
        projects.append(RawProject(
            source_id=source_id, slug=slug, title=title, description=_clean(cells[1]),
            url=link.group(2), difficulty=difficulty, estimated_hours=hours, kind="idea",
        ))
    return projects


def is_list_repo(repo: dict[str, Any]) -> bool:
    text = f"{repo.get('name', '')} {repo.get('description') or ''}"
    return bool(_LIST_REPO.search(text))


def repo_to_raw(repo: dict[str, Any], source_id: str) -> RawProject:
    """A GitHub search result as a 'make a first contribution' project."""
    name = repo["full_name"]
    description = _clean(repo.get("description") or "")
    return RawProject(
        source_id=source_id, slug=slugify(name), title=f"Contribute to {name}",
        description=(description + " " if description else "")
        + "Pick a good-first-issue, discuss it with maintainers, and get a pull request merged.",
        url=repo["html_url"], difficulty="intermediate", estimated_hours=20, kind="open_source",
        language=repo.get("language"), topics=list(repo.get("topics") or []),
        stars=repo.get("stargazers_count"),
    )


# --- Skills --------------------------------------------------------------------------------------


def _matches(pattern: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9])(?:{pattern})(?![a-z0-9])", text, re.I) is not None


@lru_cache
def _skill_names(family: str) -> dict[str, str]:
    catalog = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8"))
    return {skill["skill_id"]: skill["skill_name"] for module in catalog["families"][family]["modules"]
            for skill in module["skills"]}


def skills_for(raw: RawProject, family: str) -> tuple[list[str], list[str]]:
    """(supported_skill_ids, skill names) for one role; empty when the role doesn't fit."""
    text = ". ".join([raw.title, raw.description, raw.language or "", " ".join(raw.topics)]).replace("-", " ")
    skills: list[str] = []

    def add(ids: Iterable[str]) -> None:
        for skill in ids:
            if skill not in skills:
                skills.append(skill)

    for pattern, ids in _RULES[family]:
        if _matches(pattern, text):
            add(ids)
    language = (raw.language or "").lower()
    if family == "ai_engineer" and _matches("python", text):
        language = language or "python"
    add(_LANGUAGE_SKILLS.get(family, {}).get(language, ()))
    if not set(skills) - _GENERIC:
        return [], []
    add(_BASE_SKILLS[family])
    names = _skill_names(family)
    unknown = [skill for skill in skills if skill not in names]
    if unknown:  # a rule drifted from core_catalog.json
        raise ValueError(f"Unknown {family} skill ids: {unknown}")
    return skills, [names[skill] for skill in skills]


def _prerequisites(raw: RawProject, family: str) -> list[str]:
    prerequisites = ["Git and GitHub basics"]
    if raw.language:
        prerequisites.append(f"{raw.language} basics")
    elif family == "ai_engineer":
        prerequisites.append("Python basics")
    if raw.kind == "open_source":
        prerequisites.append("Reading an unfamiliar codebase")
    return prerequisites


def _deliverables(raw: RawProject) -> list[str]:
    if raw.kind == "open_source":
        return ["Merged pull request", "Issue discussion with maintainers", "Write-up of the change"]
    return ["Working project", "GitHub repository", "README with screenshots or a demo"]


def to_catalog_entries(raw: RawProject) -> list[dict[str, Any]]:
    """One projects.json-shaped entry per role the project practices."""
    entries = []
    for family, career_path in CAREER_PATHS.items():
        skill_ids, keywords = skills_for(raw, family)
        if not skill_ids:
            continue
        entries.append({
            "id": f"gh_{_FAMILY_PREFIX[family]}_{raw.source_id}_{raw.slug}",
            "career_path": career_path,
            "title": raw.title,
            "description": raw.description,
            "skills_practiced": keywords,
            "prerequisites": _prerequisites(raw, family),
            "difficulty": raw.difficulty,
            "estimated_hours": raw.estimated_hours,
            "deliverables": _deliverables(raw),
            "supported_skill_ids": skill_ids,
            "source": "github",
            "source_kind": raw.kind,
            "url": raw.url,
            **({"stars": raw.stars} if raw.stars is not None else {}),
        })
    return entries


# --- Fetching ------------------------------------------------------------------------------------


def create_client(token: str | None = None, transport: httpx2.BaseTransport | None = None) -> httpx2.Client:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx2.Client(headers=headers, timeout=30.0, follow_redirects=True, transport=transport)


def fetch_idea_list(client: httpx2.Client, source: dict[str, Any]) -> list[RawProject]:
    url = f"{RAW_GITHUB}/{source['repo']}/{source.get('branch', 'main')}/{source.get('path', 'README.md')}"
    request = client.build_request("GET", url)
    # Public raw files need no token, and an invalid one turns them into 404s.
    request.headers.pop("Authorization", None)
    response = client.send(request)
    response.raise_for_status()
    return parse_idea_table(response.text, source["id"])


def _search_query(source: dict[str, Any]) -> str:
    """topic:<topic>, plus good-first-issues:>N when the source asks for repos that welcome newcomers."""
    query = f"topic:{source['topic']}"
    if source.get("min_good_first_issues"):
        query += f" good-first-issues:>={int(source['min_good_first_issues'])}"
    return query


def fetch_topic(client: httpx2.Client, source: dict[str, Any]) -> list[RawProject]:
    limit = int(source.get("limit", 50))
    min_stars = int(source.get("min_stars", 0))
    projects: list[RawProject] = []
    page = 1
    while len(projects) < limit and page <= 5:
        response = client.get(f"{GITHUB_API}/search/repositories", params={
            "q": f"{_search_query(source)} archived:false fork:false stars:>={min_stars}",
            "sort": "stars", "order": "desc", "per_page": "100", "page": str(page),
        })
        response.raise_for_status()
        items = response.json().get("items", [])
        for repo in items:
            if repo.get("archived") or repo.get("fork") or not repo.get("language") or is_list_repo(repo):
                continue
            projects.append(repo_to_raw(repo, source["id"]))
            if len(projects) >= limit:
                break
        if len(items) < 100:
            break
        page += 1
    return projects


def build_catalog(raw_projects: Iterable[RawProject]) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for raw in raw_projects:
        for entry in to_catalog_entries(raw):
            entries.setdefault(entry["id"], entry)
    return sorted(entries.values(), key=lambda e: (e["career_path"], e["id"]))
