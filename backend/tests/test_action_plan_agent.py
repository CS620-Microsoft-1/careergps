import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.config import ActionPlanSettings
from app.services.action_plans import agent

ENDPOINT = "https://example.test/api/projects/demo"


def settings(version: str | None = None, endpoint: str | None = ENDPOINT) -> ActionPlanSettings:
    keys = {"ACTION_PLAN_FOUNDRY_PROJECT_ENDPOINT", "ACTION_PLAN_FOUNDRY_AGENT_NAME", "ACTION_PLAN_FOUNDRY_AGENT_VERSION"}
    with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k not in keys}, clear=True):
        return ActionPlanSettings(_env_file=None, action_plan_foundry_project_endpoint=endpoint,
                                  action_plan_foundry_agent_version=version)


class FakeFoundry:
    """Stands in for DefaultAzureCredential → AIProjectClient → get_openai_client."""

    def __init__(self, status: str = "completed", output: dict | None = None, error: Exception | None = None):
        self.client = MagicMock()
        self.client.conversations.create.return_value = SimpleNamespace(id="conv-1")
        if error:
            self.client.responses.create.side_effect = error
        else:
            self.client.responses.create.return_value = SimpleNamespace(
                status=status, output_text=json.dumps(output if output is not None else {"plans": []}))
        self.project = MagicMock()
        self.project.get_openai_client.return_value.__enter__.return_value = self.client
        project_class = MagicMock()
        project_class.return_value.__enter__.return_value = self.project
        self.patches = [patch("azure.ai.projects.AIProjectClient", project_class),
                        patch("azure.identity.DefaultAzureCredential", MagicMock())]

    def __enter__(self):
        for item in self.patches:
            item.start()
        return self

    def __exit__(self, *exc):
        for item in self.patches:
            item.stop()


class ActionPlanAgentTest(unittest.TestCase):
    def test_not_configured_raises(self) -> None:
        self.assertFalse(agent.is_configured(settings(endpoint=None)))
        with self.assertRaises(agent.ActionPlanAgentNotConfigured):
            agent.invoke({}, settings=settings(endpoint=None))

    def test_latest_binds_the_client_to_the_agent_name(self) -> None:
        with FakeFoundry(output={"plans": []}) as foundry:
            result = agent.invoke({"mode": "full"}, settings=settings("latest"))
        self.assertEqual(result, {"plans": []})
        options = foundry.project.get_openai_client.call_args.kwargs
        self.assertEqual((options["agent_name"], options["max_retries"]), ("action-plan-agent", 0))
        self.assertNotIn("extra_body", foundry.client.responses.create.call_args.kwargs)

    def test_pinned_version_goes_in_the_agent_reference(self) -> None:
        with FakeFoundry() as foundry:
            agent.invoke({"mode": "full"}, settings=settings("2"))
        self.assertNotIn("agent_name", foundry.project.get_openai_client.call_args.kwargs)
        reference = foundry.client.responses.create.call_args.kwargs["extra_body"]["agent_reference"]
        self.assertEqual(reference, {"type": "agent_reference", "name": "action-plan-agent", "version": "2"})

    def test_sends_the_payload_as_input_json(self) -> None:
        with FakeFoundry() as foundry:
            agent.invoke({"mode": "full", "job_family": "data_analyst"}, settings=settings())
        content = foundry.client.responses.create.call_args.kwargs["input"][0]["content"]
        self.assertTrue(content.startswith(agent.PROMPT))
        self.assertEqual(json.loads(content[len(agent.PROMPT):])["job_family"], "data_analyst")

    def test_deletes_the_conversation_even_on_error(self) -> None:
        with FakeFoundry(error=TimeoutError("slow")) as foundry, self.assertRaises(TimeoutError):
            agent.invoke({}, settings=settings())
        foundry.client.conversations.delete.assert_called_once_with(conversation_id="conv-1")

    def test_incomplete_response_raises(self) -> None:
        with FakeFoundry(status="incomplete"), self.assertRaises(RuntimeError):
            agent.invoke({}, settings=settings())


if __name__ == "__main__":
    unittest.main()
