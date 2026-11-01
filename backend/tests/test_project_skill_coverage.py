import json
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from app.services.resources_agent import recommend_projects


@contextmanager
def agent_returning(choices, reason=None):
    client = MagicMock()
    client.__enter__.return_value = client
    client.conversations.create.return_value.id = "test"
    client.responses.create.return_value.status = "completed"
    client.responses.create.return_value.output_text = json.dumps({"recommendations": choices, "no_match_reason": reason})
    project = MagicMock()
    project.__enter__.return_value = project
    project.get_openai_client.return_value = client
    credential = MagicMock()
    credential.__enter__.return_value = credential
    settings = MagicMock(resources_project_endpoint="test", resources_agent_name="test")
    with patch("app.services.resources_agent.get_settings", return_value=settings), patch("app.services.resources_agent.DefaultAzureCredential", return_value=credential), patch("app.services.resources_agent.AIProjectClient", return_value=project):
        yield client


class CoverageTest(unittest.TestCase):
    def test_unsupported_ai_skill_claims_and_explanations_are_removed(self):
        gaps = [
            {"skill_id": "general_programming", "skill_name": "General programming", "definition": "Non-Python languages"},
            {"skill_id": "ai_agents", "skill_name": "Agents & tool use", "definition": "Model-mediated tool invocation"},
            {"skill_id": "model_evaluation", "skill_name": "Model evaluation", "definition": "Evaluate model quality"},
            {"skill_id": "python", "skill_name": "Python development", "definition": "Python programming"},
            {"skill_id": "rag", "skill_name": "Retrieval-augmented generation", "definition": "Retrieval followed by generation"},
            {"skill_id": "model_deployment", "skill_name": "Model deployment & serving", "definition": "Serve inference"},
        ]
        choices = [
            {"project_id": "aiml_01", "addressed_gaps": ["General programming", "Python development"], "why_recommended": "Claims non-Python programming", "prerequisites_to_check": []},
            {"project_id": "aiml_02", "addressed_gaps": ["Agents & tool use", "Retrieval-augmented generation"], "why_recommended": "Claims agent tools", "prerequisites_to_check": []},
            {"project_id": "aiml_03", "addressed_gaps": ["Model evaluation", "Model deployment & serving"], "why_recommended": "Claims evaluation", "prerequisites_to_check": []},
        ]
        with agent_returning(choices) as client:
            result = recommend_projects("AI/ML Engineering", [], [g["skill_name"] for g in gaps], 40, gaps)
            self.assertEqual([r["addressed_skill_ids"] for r in result["recommendations"]], [["python"], ["rag"], ["model_deployment"]])
            for recommendation in result["recommendations"]:
                self.assertNotIn("Claims", recommendation["why_recommended"])
            empty = recommend_projects("AI/ML Engineering", [], [g["skill_name"] for g in gaps], 1, gaps)
            self.assertEqual(empty["recommendations"], [])
            self.assertIsNotNone(empty["no_match_reason"])
            self.assertEqual(client.responses.create.call_count, 1)

    def test_agent_picks_that_all_miss_the_verified_gaps_are_a_failure(self):
        gaps = [{"skill_id": "general_programming", "skill_name": "General programming", "definition": "Non-Python languages"},
                {"skill_id": "python", "skill_name": "Python development", "definition": "Python programming"}]
        choices = [{"project_id": "aiml_01", "addressed_gaps": ["General programming"], "why_recommended": "Claims non-Python programming", "prerequisites_to_check": []}]
        with agent_returning(choices), self.assertRaises(ValueError):
            recommend_projects("AI/ML Engineering", [], [g["skill_name"] for g in gaps], 40, gaps)
        with agent_returning([], "None fit."):
            self.assertEqual([], recommend_projects("AI/ML Engineering", [], [g["skill_name"] for g in gaps], 40, gaps)["recommendations"])


if __name__ == "__main__":
    unittest.main()
