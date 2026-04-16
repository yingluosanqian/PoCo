from __future__ import annotations

import unittest
from typing import Any

from poco.platform.common.message_client import MessageSendResult
from poco.platform.slack.cards import SlackCardRenderer
from poco.platform.slack.client import (
    SlackApiError,
    SlackChannelArchiveForbiddenError,
    SlackChannelCreateResult,
    SlackChannelNotFoundError,
)
from poco.platform.slack.debug import SlackDebugRecorder
from poco.platform.slack.project_bootstrap import (
    SlackProjectBootstrapper,
    _channel_name_for_project,
)
from poco.project.bootstrap import ProjectBootstrapError
from poco.project.controller import ProjectController
from poco.storage.memory import InMemoryProjectStore


class FakeSlackChannelClient:
    def __init__(
        self,
        *,
        create_fails_first: int = 0,
        archive_error: Exception | None = None,
        invite_error: Exception | None = None,
    ) -> None:
        self._create_fails_first = create_fails_first
        self._archive_error = archive_error
        self._invite_error = invite_error
        self.create_calls: list[dict[str, Any]] = []
        self.invite_calls: list[dict[str, Any]] = []
        self.archive_calls: list[dict[str, Any]] = []
        self.sent_cards: list[dict[str, Any]] = []

    def create_channel(self, *, name: str, is_private: bool = False) -> SlackChannelCreateResult:
        self.create_calls.append({"name": name, "is_private": is_private})
        if self._create_fails_first > 0:
            self._create_fails_first -= 1
            raise SlackApiError("Slack API call conversations.create failed: name_taken")
        return SlackChannelCreateResult(
            channel_id=f"C{len(self.create_calls):04d}",
            name=name,
            raw_response={"ok": True, "channel": {"id": f"C{len(self.create_calls):04d}", "name": name}},
        )

    def invite_users_to_channel(self, *, channel: str, user_ids: list[str]) -> None:
        self.invite_calls.append({"channel": channel, "user_ids": list(user_ids)})
        if self._invite_error is not None:
            raise self._invite_error

    def archive_channel(self, *, channel: str) -> None:
        self.archive_calls.append({"channel": channel})
        if self._archive_error is not None:
            raise self._archive_error

    def send_interactive(
        self, *, receive_id: str, receive_id_type: str, card: dict[str, Any]
    ) -> MessageSendResult:
        self.sent_cards.append(
            {"receive_id": receive_id, "receive_id_type": receive_id_type, "card": card}
        )
        return MessageSendResult(
            message_id="1700000000.000001",
            channel=receive_id,
        )


class ChannelNameSanitizeTest(unittest.TestCase):
    def test_simple_name_is_lowercased_and_prefixed(self) -> None:
        self.assertEqual(_channel_name_for_project("PoCo"), "poco-poco")

    def test_spaces_and_pipes_are_hyphenated(self) -> None:
        self.assertEqual(
            _channel_name_for_project("Frontend | RFC review"),
            "poco-frontend-rfc-review",
        )

    def test_non_alphanumeric_characters_are_collapsed(self) -> None:
        self.assertEqual(
            _channel_name_for_project("Ops//Team!!"),
            "poco-ops-team",
        )

    def test_empty_name_falls_back_to_project_slug(self) -> None:
        self.assertEqual(_channel_name_for_project(""), "poco-project")

    def test_max_80_chars(self) -> None:
        name = "A" * 200
        slug = _channel_name_for_project(name)
        self.assertLessEqual(len(slug), 80)
        self.assertTrue(slug.startswith("poco-"))


class SlackProjectBootstrapperTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_controller = ProjectController(InMemoryProjectStore())
        self.project = self.project_controller.create_project(
            name="PoCo Frontend",
            created_by="U1",
            backend="codex",
        )
        self.renderer = SlackCardRenderer()
        self.debug_recorder = SlackDebugRecorder()

    def test_bootstrap_creates_channel_and_invites_actor(self) -> None:
        client = FakeSlackChannelClient()
        bootstrapper = SlackProjectBootstrapper(
            client,  # type: ignore[arg-type]
            self.renderer,
            project_controller=self.project_controller,
            debug_recorder=self.debug_recorder,
        )

        result = bootstrapper.bootstrap_project(project=self.project, actor_id="U1")

        self.assertEqual(len(client.create_calls), 1)
        self.assertEqual(client.create_calls[0]["name"], "poco-poco-frontend")
        self.assertTrue(client.create_calls[0]["is_private"])
        self.assertEqual(client.invite_calls, [{"channel": "C0001", "user_ids": ["U1"]}])
        self.assertEqual(result.group_chat_id, "C0001")
        snapshot = self.debug_recorder.snapshot()
        self.assertEqual(snapshot["outbound_attempts"][0]["source"], "project_group_bootstrap")

    def test_bootstrap_retries_on_name_taken(self) -> None:
        client = FakeSlackChannelClient(create_fails_first=2)
        bootstrapper = SlackProjectBootstrapper(
            client,  # type: ignore[arg-type]
            self.renderer,
            debug_recorder=self.debug_recorder,
        )
        result = bootstrapper.bootstrap_project(project=self.project, actor_id="U1")

        names = [call["name"] for call in client.create_calls]
        self.assertEqual(
            names,
            ["poco-poco-frontend", "poco-poco-frontend-2", "poco-poco-frontend-3"],
        )
        self.assertEqual(result.group_chat_id, "C0003")

    def test_bootstrap_gives_up_after_max_attempts(self) -> None:
        client = FakeSlackChannelClient(create_fails_first=99)
        bootstrapper = SlackProjectBootstrapper(
            client,  # type: ignore[arg-type]
            self.renderer,
            debug_recorder=self.debug_recorder,
        )
        with self.assertRaises(ProjectBootstrapError):
            bootstrapper.bootstrap_project(project=self.project, actor_id="U1")
        errors = self.debug_recorder.snapshot()["errors"]
        self.assertTrue(any("Could not pick a free Slack channel name" in e["message"] for e in errors))

    def test_bootstrap_surfaces_non_name_taken_errors(self) -> None:
        class BrokenClient(FakeSlackChannelClient):
            def create_channel(self, **_kwargs):
                raise SlackApiError("Slack API call conversations.create failed: restricted_action")

        bootstrapper = SlackProjectBootstrapper(
            BrokenClient(),  # type: ignore[arg-type]
            self.renderer,
            debug_recorder=self.debug_recorder,
        )
        with self.assertRaises(ProjectBootstrapError) as caught:
            bootstrapper.bootstrap_project(project=self.project, actor_id="U1")
        self.assertIn("restricted_action", str(caught.exception))

    def test_invite_error_is_recorded_but_does_not_roll_back_channel(self) -> None:
        client = FakeSlackChannelClient(
            invite_error=SlackApiError("Slack API call conversations.invite failed: already_in_channel")
        )
        bootstrapper = SlackProjectBootstrapper(
            client,  # type: ignore[arg-type]
            self.renderer,
            debug_recorder=self.debug_recorder,
        )
        result = bootstrapper.bootstrap_project(project=self.project, actor_id="U1")
        self.assertEqual(result.group_chat_id, "C0001")
        errors = self.debug_recorder.snapshot()["errors"]
        self.assertTrue(any(e["stage"] == "project_group_bootstrap_invite" for e in errors))

    def test_notify_project_workspace_posts_card_and_binds_message(self) -> None:
        client = FakeSlackChannelClient()
        bootstrapper = SlackProjectBootstrapper(
            client,  # type: ignore[arg-type]
            self.renderer,
            project_controller=self.project_controller,
            debug_recorder=self.debug_recorder,
        )
        project = self.project_controller.bind_group(self.project.id, "C0001")
        bootstrapper.notify_project_workspace(project=project, actor_id="U1")

        self.assertEqual(len(client.sent_cards), 1)
        card = client.sent_cards[0]
        self.assertEqual(card["receive_id"], "C0001")
        self.assertEqual(card["receive_id_type"], "channel")

        refreshed = self.project_controller.get_project(project.id)
        self.assertEqual(refreshed.workspace_message_id, "1700000000.000001")
        self.assertEqual(refreshed.workspace_message_channel, "C0001")

    def test_notify_project_workspace_records_error_silently(self) -> None:
        class FailingClient(FakeSlackChannelClient):
            def send_interactive(self, **_kwargs):
                raise SlackApiError("Slack API call chat.postMessage failed: channel_not_found")

        bootstrapper = SlackProjectBootstrapper(
            FailingClient(),  # type: ignore[arg-type]
            self.renderer,
            project_controller=self.project_controller,
            debug_recorder=self.debug_recorder,
        )
        project = self.project_controller.bind_group(self.project.id, "C0001")
        bootstrapper.notify_project_workspace(project=project, actor_id="U1")  # Should not raise.

        errors = self.debug_recorder.snapshot()["errors"]
        self.assertTrue(any(e["stage"] == "project_workspace_bootstrap" for e in errors))

    def test_destroy_archives_channel(self) -> None:
        client = FakeSlackChannelClient()
        bootstrapper = SlackProjectBootstrapper(
            client,  # type: ignore[arg-type]
            self.renderer,
            debug_recorder=self.debug_recorder,
        )
        project = self.project_controller.bind_group(self.project.id, "C0001")
        bootstrapper.destroy_project_workspace(project=project, actor_id="U1")
        self.assertEqual(client.archive_calls, [{"channel": "C0001"}])

    def test_destroy_raises_bootstrap_error_on_missing_channel(self) -> None:
        client = FakeSlackChannelClient(
            archive_error=SlackChannelNotFoundError("channel_not_found")
        )
        bootstrapper = SlackProjectBootstrapper(
            client,  # type: ignore[arg-type]
            self.renderer,
            debug_recorder=self.debug_recorder,
        )
        project = self.project_controller.bind_group(self.project.id, "C0001")
        with self.assertRaises(ProjectBootstrapError) as caught:
            bootstrapper.destroy_project_workspace(project=project, actor_id="U1")
        self.assertIn("not found", str(caught.exception))

    def test_destroy_raises_bootstrap_error_on_forbidden_archive(self) -> None:
        client = FakeSlackChannelClient(
            archive_error=SlackChannelArchiveForbiddenError("cant_archive_general")
        )
        bootstrapper = SlackProjectBootstrapper(
            client,  # type: ignore[arg-type]
            self.renderer,
            debug_recorder=self.debug_recorder,
        )
        project = self.project_controller.bind_group(self.project.id, "C0001")
        with self.assertRaises(ProjectBootstrapError) as caught:
            bootstrapper.destroy_project_workspace(project=project, actor_id="U1")
        self.assertIn("Archive it manually", str(caught.exception))

    def test_destroy_requires_bound_channel(self) -> None:
        client = FakeSlackChannelClient()
        bootstrapper = SlackProjectBootstrapper(
            client,  # type: ignore[arg-type]
            self.renderer,
        )
        with self.assertRaises(ProjectBootstrapError):
            bootstrapper.destroy_project_workspace(project=self.project, actor_id="U1")


if __name__ == "__main__":
    unittest.main()
