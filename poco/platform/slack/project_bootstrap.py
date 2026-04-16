from __future__ import annotations

import re

from poco.interaction.card_dispatcher import build_render_instruction
from poco.interaction.card_handlers import build_workspace_overview_result
from poco.interaction.card_models import Surface
from poco.platform.slack.cards import SlackCardRenderer
from poco.platform.slack.client import (
    SlackApiError,
    SlackChannelArchiveForbiddenError,
    SlackChannelNotFoundError,
    SlackMessageClient,
)
from poco.platform.slack.debug import SlackDebugRecorder
from poco.project.bootstrap import (
    ProjectBootstrapError,
    ProjectBootstrapResult,
)
from poco.project.controller import ProjectController
from poco.project.models import Project


_CHANNEL_NAME_SANITIZER = re.compile(r"[^a-z0-9_-]+")


class SlackProjectBootstrapper:
    """Create a Slack channel for a project and post a workspace card.

    Mirrors :class:`poco.platform.feishu.project_bootstrap.FeishuProjectBootstrapper`.
    Because Slack has no single-step "create group and invite owner" API,
    this bootstrapper calls ``conversations.create`` then immediately
    ``conversations.invite`` for the actor. Channel names are sanitized to
    Slack's constraints (lowercase alphanumerics/hyphens/underscores) with
    a ``poco-`` prefix and a numeric suffix if the normalised name
    collides.
    """

    MAX_NAME_SUFFIX_ATTEMPTS = 5

    def __init__(
        self,
        message_client: SlackMessageClient,
        renderer: SlackCardRenderer,
        *,
        project_controller: ProjectController | None = None,
        debug_recorder: SlackDebugRecorder | None = None,
        is_private: bool = True,
    ) -> None:
        self._message_client = message_client
        self._renderer = renderer
        self._project_controller = project_controller
        self._debug_recorder = debug_recorder
        self._is_private = is_private

    def bootstrap_project(
        self,
        *,
        project: Project,
        actor_id: str,
    ) -> ProjectBootstrapResult:
        base_name = _channel_name_for_project(project.name)
        last_error: SlackApiError | None = None
        for attempt in range(self.MAX_NAME_SUFFIX_ATTEMPTS):
            candidate = base_name if attempt == 0 else f"{base_name}-{attempt + 1}"
            try:
                created = self._message_client.create_channel(
                    name=candidate,
                    is_private=self._is_private,
                )
                break
            except SlackApiError as exc:
                detail = str(exc)
                if "name_taken" in detail:
                    last_error = exc
                    continue
                self._record_error(
                    stage="project_group_bootstrap",
                    message=detail,
                    project=project,
                    actor_id=actor_id,
                )
                raise ProjectBootstrapError(detail) from exc
        else:
            message = (
                f"Could not pick a free Slack channel name based on '{base_name}'."
            )
            self._record_error(
                stage="project_group_bootstrap",
                message=message,
                project=project,
                actor_id=actor_id,
            )
            raise ProjectBootstrapError(message) from last_error

        try:
            self._message_client.invite_users_to_channel(
                channel=created.channel_id,
                user_ids=[actor_id] if actor_id else [],
            )
        except SlackApiError as exc:
            # Invites can fail for an already-a-member case; record but
            # don't unwind the channel creation — the operator may prefer
            # to keep the channel and invite manually.
            self._record_error(
                stage="project_group_bootstrap_invite",
                message=str(exc),
                project=project,
                actor_id=actor_id,
            )

        if self._debug_recorder is not None:
            self._debug_recorder.record_outbound_attempt(
                source="project_group_bootstrap",
                channel=created.channel_id,
                text=f"{created.name or base_name} -> {created.channel_id}",
                task_id=project.id,
            )
        return ProjectBootstrapResult(group_chat_id=created.channel_id)

    def notify_project_workspace(
        self,
        *,
        project: Project,
        actor_id: str,
    ) -> None:
        if not project.group_chat_id:
            return

        result = build_workspace_overview_result(project)
        instruction = build_render_instruction(result, surface=Surface.GROUP)
        card = self._renderer.render(instruction)
        try:
            send_result = self._message_client.send_interactive(
                receive_id=project.group_chat_id,
                receive_id_type="channel",
                card=card,
            )
        except SlackApiError as exc:
            self._record_error(
                stage="project_workspace_bootstrap",
                message=str(exc),
                project=project,
                actor_id=actor_id,
            )
            return

        if self._project_controller is not None and send_result.message_id:
            self._project_controller.bind_workspace_message(
                project.id,
                send_result.message_id,
                channel=send_result.channel or project.group_chat_id,
            )

        if self._debug_recorder is not None:
            self._debug_recorder.record_outbound_attempt(
                source="project_workspace_bootstrap",
                channel=project.group_chat_id,
                text=f"[card] Workspace: {project.name}",
                task_id=project.id,
            )

    def destroy_project_workspace(
        self,
        *,
        project: Project,
        actor_id: str,
    ) -> None:
        if not project.group_chat_id:
            raise ProjectBootstrapError("Project group not found.")
        try:
            self._message_client.archive_channel(channel=project.group_chat_id)
        except SlackChannelNotFoundError as exc:
            self._record_error(
                stage="project_group_destroy",
                message=str(exc),
                project=project,
                actor_id=actor_id,
            )
            raise ProjectBootstrapError("Project group not found.") from exc
        except SlackChannelArchiveForbiddenError as exc:
            self._record_error(
                stage="project_group_destroy",
                message=str(exc),
                project=project,
                actor_id=actor_id,
            )
            raise ProjectBootstrapError(
                "Project group could not be archived by the app. Archive it manually in Slack, or keep the channel and only delete the project record."
            ) from exc
        except SlackApiError as exc:
            self._record_error(
                stage="project_group_destroy",
                message=str(exc),
                project=project,
                actor_id=actor_id,
            )
            raise ProjectBootstrapError(str(exc)) from exc

    def _record_error(
        self,
        *,
        stage: str,
        message: str,
        project: Project,
        actor_id: str,
    ) -> None:
        if self._debug_recorder is None:
            return
        self._debug_recorder.record_error(
            stage=stage,
            message=message,
            context={
                "project_id": project.id,
                "project_name": project.name,
                "group_chat_id": project.group_chat_id,
                "actor_id": actor_id,
            },
        )


def _channel_name_for_project(project_name: str) -> str:
    """Normalize ``project_name`` into a Slack-safe channel slug.

    Slack channels are lowercased, alphanumeric plus ``-`` / ``_``, 80 chars
    max. Empty names fall back to ``poco-project``.
    """

    slug = _CHANNEL_NAME_SANITIZER.sub("-", project_name.strip().lower())
    slug = slug.strip("-_") or "project"
    candidate = f"poco-{slug}"
    if len(candidate) > 80:
        candidate = candidate[:80].rstrip("-_") or "poco-project"
    return candidate
