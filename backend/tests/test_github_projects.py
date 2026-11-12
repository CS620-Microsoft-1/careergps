import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2

from app.services import resources
from app.services.github_projects import (
    RawProject,
    build_catalog,
    create_client,
    fetch_idea_list,
    fetch_topic,
    parse_idea_table,
    skills_for,
)
from app.services.resources_agent import MAX_AGENT_CANDIDATES, _shortlist, rank_projects

README = """
## Projects
| Tier | Developer Profile |
| :--: | --- |
|  1   | Developers in the early stages of their learning journey. |

### Tier-1: Beginner Projects
| Name | Short Description | Tier |
| :--- | :--- | :--- |
| [Password Generator](https://www.youtube.com/watch?v=a) | Password Generator App using Python | 1-Beginner |
| [Movie Recomendation Engine](https://www.youtube.com/watch?v=b)| A Movie Recommendation System Using ML|2-Intermediate|
|  [Discord Clone - MERN STACK ](https://www.youtube.com/watch?v=c) | Discord Clone App using MERN Stack |3-Advanced |
| [Password Generator](https://www.youtube.com/watch?v=dup) | duplicate row | 1-Beginner |

## Awesome Tutorials
| TOPIC | TUTOR |
| --- | --- |
| [React JS Tutorial](https://www.youtube.com/watch?v=d) | FreeCodeCamp |
"""


def _repo(name, description, language="Python", topics=(), **extra):
    return {"full_name": name, "name": name.split("/")[1], "description": description, "language": language,
            "topics": list(topics), "html_url": f"https://github.com/{name}", "stargazers_count": 500,
            "archived": False, "fork": False, **extra}


SEARCH = {"items": [
    _repo("acme/rag-chat", "A RAG chatbot over your docs with LangChain and a vector database",
          topics=["llm", "open-source-projects"]),
    _repo("acme/awesome-oss", "A curated list of open source projects"),
    _repo("acme/old", "Django REST API", archived=True),
    _repo("acme/dash", "Interactive dashboards with Streamlit and pandas for exploratory data analysis"),
    _repo("acme/no-lang", "A web app with React", language=None),
    _repo("acme/shop", "E-commerce site built with Next.js, PostgreSQL and Docker", language="TypeScript"),
]}


def _transport(request: httpx2.Request) -> httpx2.Response:
    if request.url.host == "raw.githubusercontent.com":
        assert "authorization" not in request.headers
        return httpx2.Response(200, text=README)
    if request.url.path == "/search/repositories":
        assert "topic:open-source-projects" in request.url.params["q"]
        return httpx2.Response(200, json=SEARCH)
    return httpx2.Response(404)


class ParseTest(unittest.TestCase):
    def test_only_project_rows_are_parsed_once_each(self):
        projects = parse_idea_table(README, "cool")
        self.assertEqual([p.title for p in projects],
                         ["Password Generator", "Movie Recomendation Engine", "Discord Clone - MERN STACK"])
        self.assertEqual([p.difficulty for p in projects], ["beginner", "intermediate", "advanced"])
        self.assertEqual(projects[2].description, "Discord Clone App using MERN Stack")

    def test_skills_are_role_specific(self):
        mern = RawProject("s", "x", "Discord Clone", "Clone using MERN Stack", "u", "advanced", 50, "idea")
        self.assertEqual(skills_for(mern, "software_engineer")[0],
                         ["frontend", "backend_apis", "nosql_search"])
        self.assertEqual(skills_for(mern, "ai_engineer"), ([], []))
        self.assertEqual(skills_for(mern, "data_analyst"), ([], []))
        # Python alone is not an AI project.
        python_only = RawProject("s", "y", "Password Generator", "App using Python", "u", "beginner", 15, "idea")
        self.assertEqual(skills_for(python_only, "ai_engineer"), ([], []))
        # Nor is any repo a programming or version-control project just for being code on GitHub.
        self.assertEqual(skills_for(python_only, "software_engineer"), ([], []))


class ColumnLayoutTest(unittest.TestCase):
    def test_numbered_table_without_tiers_and_role_limits(self):
        markdown = """
| S.No | Project Name | Description |
| --- | --- | --- |
| 01. | [Mall Customer Segmentation](Mall%20Customer%20Segmentation) | Segment mall customers by spending with clustering. |
| 02. | [Fake News Detection](https://github.com/o/r/tree/main/Fake) | Detect fake news articles with NLP. |
| [Contributor](https://github.com/someone) | thanks |
"""
        projects = parse_idea_table(markdown, "kart", title_column=1, description_column=2, tier_column=None,
                                    difficulty="intermediate", hours=25, link_base="https://github.com/o/r/tree/main")
        self.assertEqual([p.title for p in projects], ["Mall Customer Segmentation", "Fake News Detection"])
        self.assertEqual(projects[0].url, "https://github.com/o/r/tree/main/Mall%20Customer%20Segmentation")
        self.assertEqual((projects[0].difficulty, projects[0].estimated_hours), ("intermediate", 25))
        for project in projects:
            project.roles = ("ai_engineer", "data_analyst")
        paths = {(e["title"], e["career_path"]) for e in build_catalog(projects)}
        self.assertIn(("Mall Customer Segmentation", "Data Analyst"), paths)
        self.assertIn(("Fake News Detection", "AI/ML Engineering"), paths)
        self.assertFalse(any(path == "Software Engineering" for _, path in paths))


class FetchTest(unittest.TestCase):
    def test_idea_list_and_topic_become_catalog_entries(self):
        with create_client("bad-token", transport=httpx2.MockTransport(_transport)) as client:
            ideas = fetch_idea_list(client, {"id": "cool", "repo": "o/r"})
            repos = fetch_topic(client, {"id": "oss", "topic": "open-source-projects", "limit": 10})
        self.assertEqual(len(ideas), 3)
        self.assertEqual([p.slug for p in repos], ["acme_rag_chat", "acme_dash", "acme_shop"])
        catalog = build_catalog([*ideas, *repos])
        by_id = {entry["id"]: entry for entry in catalog}
        rag = by_id["gh_aiml_oss_acme_rag_chat"]
        self.assertEqual(rag["career_path"], "AI/ML Engineering")
        self.assertTrue({"rag", "vector_retrieval", "ai_agents", "llm", "python"} <= set(rag["supported_skill_ids"]))
        self.assertEqual(rag["url"], "https://github.com/acme/rag-chat")
        self.assertIn("gh_data_oss_acme_dash", by_id)
        self.assertIn("gh_swe_oss_acme_shop", by_id)
        self.assertTrue({"relational_sql", "containers"} <= set(by_id["gh_swe_oss_acme_shop"]["supported_skill_ids"]))
        for entry in catalog:
            self.assertTrue(entry["skills_practiced"])
            self.assertEqual(len(entry["skills_practiced"]), len(entry["supported_skill_ids"]))


class CatalogMergeTest(unittest.TestCase):
    def test_load_projects_merges_github_entries_and_ranking_uses_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            extra = Path(tmp) / "github_projects.json"
            with create_client(transport=httpx2.MockTransport(_transport)) as client:
                catalog = build_catalog(fetch_topic(client, {"id": "oss", "topic": "open-source-projects"}))
            extra.write_text(json.dumps(catalog), encoding="utf-8")
            resources.load_projects.cache_clear()
            try:
                with patch.object(resources, "GITHUB_PROJECTS_PATH", extra):
                    ids = [p["id"] for p in resources.load_projects()]
                    self.assertIn("swe_01", ids)
                    self.assertIn("gh_aiml_oss_acme_rag_chat", ids)
                    self.assertEqual(len(ids), len(set(ids)))
                    # No hand-written project practices agents & tool use; the GitHub repo does.
                    gaps = [{"skill_id": "ai_agents", "skill_name": "Agents & tool use", "definition": ""}]
                    picks = rank_projects("AI/ML Engineering", [], ["Agents & tool use"], None, gaps)
                    self.assertIn("gh_aiml_oss_acme_rag_chat", [r["project_id"] for r in picks["recommendations"]])
                    listed = {r["id"]: r for r in resources.resources_for("ai_engineer", None)}
                    self.assertTrue(all(r["provider"] == "" for r in listed.values() if r["type"] == "project"))
                    self.assertEqual(listed["gh_aiml_oss_acme_rag_chat"]["url"], "https://github.com/acme/rag-chat")
            finally:
                resources.load_projects.cache_clear()

    def test_projects_name_no_provider(self):
        idea = {"id": "gh_swe_cool_x", "title": "Weather App", "difficulty": "beginner", "estimated_hours": 15,
                "description": "", "supported_skill_ids": ["frontend"], "source": "github", "source_kind": "idea",
                "url": "https://www.youtube.com/watch?v=x"}
        self.assertEqual(resources._project(idea)["provider"], "")

    def test_agent_shortlist_keeps_best_covering_projects(self):
        gaps = [{"skill_id": "rag", "skill_name": "RAG", "definition": ""},
                {"skill_id": "llm", "skill_name": "LLM", "definition": ""}]
        filler = [{"id": f"f{i}", "supported_skill_ids": ["llm"]} for i in range(40)]
        best = {"id": "best", "supported_skill_ids": ["rag", "llm"]}
        shortlist = _shortlist([*filler, best], gaps, [])
        self.assertEqual(len(shortlist), MAX_AGENT_CANDIDATES)
        self.assertEqual(shortlist[0]["id"], "best")


if __name__ == "__main__":
    unittest.main()
