import logging
import unittest
from types import SimpleNamespace

from poco.relay.cards import SetupCardController


class _FakeWorkerStore:
    def __init__(self) -> None:
        self.provider_calls = []
        self.backend_calls = []
        self.model_calls = []

    def set_provider(self, worker_id: str, selected: str) -> None:
        self.provider_calls.append((worker_id, selected))

    def set_backend(self, worker_id: str, selected: str) -> None:
        self.backend_calls.append((worker_id, selected))

    def set_model(self, worker_id: str, selected: str) -> None:
        self.model_calls.append((worker_id, selected))

    def alias_in_use(self, alias: str) -> bool:
        return False

    def backend_for(self, worker_id: str) -> str:
        return "openai"

    def cwd_for(self, worker_id: str) -> str:
        return ""

    def set_alias(self, worker_id: str, alias: str) -> None:
        return None

    def set_cwd(self, worker_id: str, cwd: str) -> None:
        return None


class _FakeApp:
    def __init__(self) -> None:
        self.LOG = logging.getLogger("test.cards")
        self._worker_store = _FakeWorkerStore()
        self._config = SimpleNamespace(claude_default_backend="anthropic", claude_backends={})

    def _provider_name_for_worker(self, worker_id: str) -> str:
        return "codex"

    def _recycle_worker_runtime(self, worker_id: str, *, reason: str) -> None:
        return None

    def _claude_backend_name(self, worker_id: str) -> str:
        return "anthropic"

    def _reply_mode_label(self, mode: str) -> str:
        return mode

    def _merge_project_draft(self, chat_id: str, **updates: str) -> dict:
        return {
            "provider": "codex",
            "backend": "openai",
            "model": "gpt-5.4",
            "mode": "auto",
            "session_id": updates.get("session_id", ""),
            "project_id": updates.get("project_id", ""),
            "cwd": updates.get("cwd", ""),
        }

    def _normalize_alias(self, alias: str):
        return None

    def _worker_store_alias_in_use(self, alias: str) -> bool:
        return False

    def _validate_cwd(self, cwd: str):
        return None

    def _create_project_group_from_dm(self, *args, **kwargs) -> str:
        return "oc_test"


class SetupCardHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _FakeApp()
        self.controller = SetupCardController(self.app)

    def test_dm_mode_root_uses_dm_console_response(self) -> None:
        sentinel = object()

        def dm_console_response(**kwargs):
            self.assertEqual(kwargs.get("mode"), "root")
            return sentinel

        result = self.controller._handle_dm_card_action(
            action_name="dm_mode_root",
            action=None,
            action_value={},
            form_value={},
            chat_id="ou_dm_chat",
            dm_console_response=dm_console_response,
        )
        self.assertIs(result, sentinel)

    def test_set_provider_updates_store(self) -> None:
        action = SimpleNamespace(option="codex")

        def current_card(notice: str = "", toast_type: str = "info", **kwargs):
            return {"notice": notice, "toast_type": toast_type, **kwargs}

        result = self.controller._handle_setup_selection_action(
            action_name="set_provider",
            action=action,
            worker_id="oc_worker",
            current_card=current_card,
        )
        self.assertEqual(self.app._worker_store.provider_calls, [("oc_worker", "codex")])
        self.assertEqual(self.app._worker_store.backend_calls, [("oc_worker", "openai")])
        self.assertEqual(result["notice"], "Agent set to codex.")

    def test_launch_project_invalid_alias_returns_error(self) -> None:
        captured = {}

        def project_card_response(notice: str = "", toast_type: str = "info", **kwargs):
            captured["notice"] = notice
            captured["toast_type"] = toast_type
            captured["kwargs"] = kwargs
            return captured

        result = self.controller._handle_project_launch_action(
            action_name="launch_project",
            form_value={"project_id": "INVALID_ID", "cwd": "/tmp", "session_id": ""},
            chat_id="ou_dm_chat",
            event=SimpleNamespace(operator=SimpleNamespace(open_id="ou_xxx")),
            project_card_response=project_card_response,
        )
        self.assertIs(result, captured)
        self.assertEqual(captured["toast_type"], "error")
        self.assertIn("Project ID is invalid", captured["notice"])


if __name__ == "__main__":
    unittest.main()
