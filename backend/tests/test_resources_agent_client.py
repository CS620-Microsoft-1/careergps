import json
import unittest
from unittest.mock import MagicMock, patch

from app.services.resources_agent import recommend_projects


class ResourcesAgentClientTest(unittest.TestCase):
    def test_agent_client_does_not_retry(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.conversations.create.return_value.id = "test"
        client.responses.create.return_value.status = "completed"
        client.responses.create.return_value.output_text = json.dumps({"recommendations": [], "no_match_reason": "none fit"})
        project = MagicMock()
        project.__enter__.return_value = project
        project.get_openai_client.return_value = client
        credential = MagicMock()
        credential.__enter__.return_value = credential
        settings = MagicMock(resources_project_endpoint="test", resources_agent_name="test")
        with patch("app.services.resources_agent.get_settings", return_value=settings), \
             patch("app.services.resources_agent.DefaultAzureCredential", return_value=credential), \
             patch("app.services.resources_agent.AIProjectClient", return_value=project):
            recommend_projects("AI/ML Engineering", [], ["Python development"], None)
        self.assertEqual(project.get_openai_client.call_args.kwargs.get("max_retries"), 0)


if __name__ == "__main__":
    unittest.main()
