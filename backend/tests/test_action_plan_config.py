import os
import unittest
from unittest.mock import patch

from app.core.config import ActionPlanSettings

KEYS = ("ACTION_PLAN_FOUNDRY_PROJECT_ENDPOINT", "ACTION_PLAN_FOUNDRY_AGENT_NAME",
        "ACTION_PLAN_FOUNDRY_AGENT_VERSION")


def settings(**env: str) -> ActionPlanSettings:
    """Settings from the given variables only: no backend/.env, no other ACTION_PLAN_* values."""
    clean = {key: value for key, value in os.environ.items() if key not in KEYS}
    with patch.dict(os.environ, {**clean, **env}, clear=True):
        return ActionPlanSettings(_env_file=None)


class ActionPlanSettingsTest(unittest.TestCase):
    def test_defaults_leave_the_agent_unconfigured(self) -> None:
        value = settings()
        self.assertIsNone(value.action_plan_foundry_project_endpoint)
        self.assertEqual(value.action_plan_foundry_agent_name, "action-plan-agent")
        self.assertIsNone(value.action_plan_foundry_agent_version)
        self.assertIsNone(value.pinned_agent_version)

    def test_reads_values_from_the_environment(self) -> None:
        value = settings(ACTION_PLAN_FOUNDRY_PROJECT_ENDPOINT="https://example.test/api/projects/demo",
                         ACTION_PLAN_FOUNDRY_AGENT_NAME="other-agent",
                         ACTION_PLAN_FOUNDRY_AGENT_VERSION="3")
        self.assertEqual(value.action_plan_foundry_project_endpoint, "https://example.test/api/projects/demo")
        self.assertEqual(value.action_plan_foundry_agent_name, "other-agent")
        self.assertEqual(value.pinned_agent_version, "3")

    def test_latest_or_blank_version_is_not_pinned(self) -> None:
        for version in ("latest", "LATEST", " latest ", "", "  "):
            with self.subTest(version=version):
                self.assertIsNone(settings(ACTION_PLAN_FOUNDRY_AGENT_VERSION=version).pinned_agent_version)


if __name__ == "__main__":
    unittest.main()
