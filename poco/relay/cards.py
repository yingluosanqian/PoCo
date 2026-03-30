"""Setup card rendering and card action handling for the Feishu relay."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

if TYPE_CHECKING:
    from .app import RelayApp


class SetupCardController:
    """Owns setup-card rendering, static card helpers, and card callbacks."""

    def __init__(self, app: "RelayApp") -> None:
        self.app = app

    def setup_card(
        self,
        chat_id: str,
        worker_id: str,
        *,
        notice: str = "",
        form_alias: str = "",
        form_cwd: str = "",
        read_only: bool = False,
    ) -> dict:
        provider_name = self.app._provider_name_for_worker(worker_id)
        alias = form_alias if form_alias else self.app._worker_store.alias_for(worker_id)
        cwd = form_cwd if form_cwd else self.app._worker_store.cwd_for(worker_id)
        enabled = self.app._worker_store.enabled_for(worker_id)
        vendor = self.app._vendor_name_for_worker(worker_id)
        model = self.app._worker_store.model_for(worker_id) or self.app._effective_model_for_worker(worker_id)
        cwd_error = self.app._validate_cwd(cwd) if cwd else ""
        if read_only:
            return self._readonly_setup_card(worker_id, alias=alias, cwd=cwd)
        elements: List[dict] = []
        elements.extend(
            self.app._card_choice_group(
                "Agent",
                provider_name,
                "set_provider",
                [("codex", "codex"), ("claude code", "claude")],
            )
        )
        vendor_choices = [(item, item) for item in self.app._backend_choices_for_worker(worker_id)]
        if vendor_choices:
            elements.extend(
                self.app._card_select(
                    "Provider",
                    "set_backend",
                    vendor,
                    vendor_choices,
                    placeholder="Choose a provider",
                )
            )
        model_choices = [(item, item) for item in self.app._model_choices_for_worker(worker_id)]
        if model_choices:
            elements.extend(
                self.app._card_select(
                    "Model",
                    "set_model",
                    model,
                    model_choices,
                    placeholder="Choose a model",
                )
            )
        elements.extend(
            self.app._card_choice_group(
                "Reply Mode",
                self.app._worker_store.mode_for(worker_id),
                "set_mode",
                [("mention only", "mention"), ("all", "auto")],
            )
        )
        elements.append(
            {
                "tag": "form",
                "element_id": "setup_form",
                "name": "setup_form",
                "vertical_spacing": "8px",
                "elements": [
                    {
                        "tag": "markdown",
                        "element_id": "setup_alias_label",
                        "content": "<font color='orange-700'>**Project ID**</font>",
                    },
                    {
                        "tag": "input",
                        "element_id": "setup_alias",
                        "name": "alias",
                        "placeholder": {"tag": "plain_text", "content": "unique project id"},
                        "default_value": alias,
                    },
                    {
                        "tag": "markdown",
                        "element_id": "setup_cwd_label",
                        "content": "<font color='orange-700'>**Working Dir**</font>",
                    },
                    {
                        "tag": "input",
                        "element_id": "setup_cwd",
                        "name": "cwd",
                        "placeholder": {"tag": "plain_text", "content": "/root/project/..."},
                        "default_value": cwd,
                    },
                    {
                        "tag": "column_set",
                        "flex_mode": "flow",
                        "horizontal_spacing": "8px",
                        "columns": [
                            {
                                "tag": "column",
                                "width": "auto",
                                "elements": [
                                    self.app._card_button(
                                        "Start",
                                        "enable_setup",
                                        "primary",
                                        name="enable_setup",
                                        form_action_type="submit",
                                    )
                                ],
                            },
                            {
                                "tag": "column",
                                "width": "auto",
                                "elements": [
                                    self.app._card_button(
                                        "Reset",
                                        "reset_config",
                                        "default",
                                    )
                                ],
                            },
                        ],
                    },
                ],
            }
        )
        if cwd_error:
            elements.append(
                {
                    "tag": "markdown",
                    "element_id": "cwd_error_md",
                    "content": f"**Path check:** {cwd_error}",
                }
            )
        return {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "width_mode": "compact",
                "enable_forward": True,
                "style": {
                    "color": {
                        "brand-soft": {
                            "light_mode": "rgba(255,243,229,1)",
                            "dark_mode": "rgba(59,26,2,0.85)",
                        },
                        "brand-accent": {
                            "light_mode": "rgba(164,73,4,1)",
                            "dark_mode": "rgba(243,135,27,1)",
                        },
                    }
                },
            },
            "header": {
                "template": "orange",
                "padding": "12px 14px 10px 14px",
                "title": {"tag": "plain_text", "content": "PoCo Project Setup"},
                "text_tag_list": [
                    {
                        "tag": "text_tag",
                        "text": {
                            "tag": "plain_text",
                            "content": "Enabled" if enabled else "Disabled",
                        },
                        "color": "green" if enabled else "neutral",
                    }
                ],
            },
            "body": {
                "padding": "14px",
                "vertical_spacing": "8px",
                "elements": elements,
            },
        }

    def _readonly_setup_card(self, worker_id: str, *, alias: str, cwd: str) -> dict:
        provider_name = self.app._provider_name_for_worker(worker_id)
        vendor = self.app._vendor_name_for_worker(worker_id)
        model = self.app._worker_store.model_for(worker_id) or self.app._effective_model_for_worker(worker_id)
        mode = self.app._reply_mode_label(self.app._worker_store.mode_for(worker_id))
        rows: List[dict] = []
        if provider_name:
            rows.extend(
                self.app._card_selectable_summary_row(
                    "Agent",
                    "codex" if provider_name == "codex" else "claude code",
                )
            )
        if vendor:
            rows.extend(self.app._card_selectable_summary_row("Provider", vendor))
        if model:
            rows.extend(self.app._card_selectable_summary_row("Model", model))
        rows.extend(self.app._card_selectable_summary_row("Reply Mode", mode))
        rows.append(
            {
                "tag": "markdown",
                "element_id": "readonly_alias_label",
                "content": "<font color='orange-700'>**Project ID**</font>",
            }
        )
        rows.append(
            {
                "tag": "markdown",
                "element_id": "readonly_alias_value",
                "content": alias or "-",
            }
        )
        rows.append(
            {
                "tag": "markdown",
                "element_id": "readonly_cwd_label",
                "content": "<font color='orange-700'>**Working Dir**</font>",
            }
        )
        rows.append(
            {
                "tag": "markdown",
                "element_id": "readonly_cwd_value",
                "content": cwd or "-",
            }
        )
        return {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "width_mode": "compact",
                "enable_forward": True,
            },
            "header": {
                "template": "green",
                "padding": "12px 14px 10px 14px",
                "title": {"tag": "plain_text", "content": "PoCo Project Running"},
                "text_tag_list": [
                    {
                        "tag": "text_tag",
                        "text": {
                            "tag": "plain_text",
                            "content": "Enabled",
                        },
                        "color": "green",
                    }
                ],
            },
            "body": {
                "padding": "14px",
                "vertical_spacing": "8px",
                "elements": rows,
            },
        }

    def minimal_test_card(self, notice: str = "") -> dict:
        elements: List[dict] = [
            {
                "tag": "markdown",
                "element_id": "intro_md",
                "content": "**PoCo Card Test**\nClick the button to verify `card.action.trigger`.",
            },
            self.app._card_button("Ping", "test_ping", "primary"),
        ]
        if notice:
            elements.append(
                {
                    "tag": "markdown",
                    "element_id": "notice_md",
                    "content": f"**Notice**: {notice}",
                }
            )
        return {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "width_mode": "fill",
                "enable_forward": True,
            },
            "header": {
                "template": "orange",
                "title": {"tag": "plain_text", "content": "PoCo Card Test"},
            },
            "body": {
                "padding": "14px",
                "vertical_spacing": "8px",
                "elements": elements,
            },
        }

    def project_ready_card(
        self,
        *,
        project_id: str,
        provider_name: str,
        backend: str,
        model: str,
        mode: str,
        cwd: str,
    ) -> dict:
        """Build the welcome card shown in a newly created project group."""
        return {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "width_mode": "compact",
                "enable_forward": True,
            },
            "header": {
                "template": "green",
                "padding": "12px 14px 10px 14px",
                "title": {"tag": "plain_text", "content": "Pocket Project Ready"},
                "text_tag_list": [
                    {
                        "tag": "text_tag",
                        "text": {"tag": "plain_text", "content": "Running"},
                        "color": "green",
                    }
                ],
            },
            "body": {
                "padding": "14px",
                "vertical_spacing": "8px",
                "elements": [
                    {
                        "tag": "markdown",
                        "element_id": "project_ready_md",
                        "content": "\n".join(
                            [
                                f"**Project ID**: {project_id}",
                                f"**Agent**: {provider_name}",
                                f"**Provider**: {backend}",
                                f"**Model**: {model}",
                                f"**Reply Mode**: {self.app._reply_mode_label(mode)}",
                                f"**Working Dir**: `{cwd}`",
                                "",
                                "Directly chat in this group to start working.",
                            ]
                        ),
                    }
                ],
            },
        }

    def project_launch_card(
        self,
        chat_id: str,
        *,
        notice: str = "",
        form_project_id: str = "",
        form_cwd: str = "",
        form_session_id: str = "",
    ) -> dict:
        """Build the DM project-launch card.

        Args:
            chat_id: The DM chat id. Present for symmetry with setup_card.
            notice: Optional validation or status note to render in the card.
            form_project_id: Prefilled project id.
            form_cwd: Prefilled working directory.

        Returns:
            A Feishu card JSON 2.0 payload.
        """
        draft = self.app._project_draft(chat_id)
        project_id = form_project_id if form_project_id else draft.get("project_id", "")
        cwd = form_cwd if form_cwd else draft.get("cwd", "")
        provider_name = draft.get("provider", "codex")
        backend = draft.get("backend", "openai")
        model = draft.get("model", "gpt-5.4")
        mode = draft.get("mode", "auto")
        session_id = form_session_id if form_session_id else draft.get("session_id", "")
        elements: List[dict] = []
        elements.extend(
            self.app._card_choice_group(
                "Agent *",
                provider_name,
                "dm_project_set_provider",
                [("codex", "codex"), ("claude code", "claude")],
            )
        )
        elements.extend(
            self.app._card_choice_group(
                "Reply Mode *",
                mode,
                "dm_project_set_mode",
                [("mention only", "mention"), ("all", "auto")],
            )
        )
        backend_choices = [(item, item) for item in self.app._backend_choices_for_project_draft(chat_id)]
        model_choices = [(item, item) for item in self.app._model_choices_for_project_draft(chat_id)]
        if backend_choices:
            elements.extend(
                self.app._card_select(
                    "Provider *",
                    "dm_project_set_backend",
                    backend,
                    backend_choices,
                    placeholder="Choose a provider",
                )
            )
        if model_choices:
            elements.extend(
                self.app._card_select(
                    "Model *",
                    "dm_project_set_model",
                    model,
                    model_choices,
                    placeholder="Choose a model",
                )
            )
        def form_input_row(
            label: str,
            *,
            element_id: str,
            name: str,
            placeholder: str,
            default_value: str,
        ) -> dict:
            return {
                "tag": "column_set",
                "flex_mode": "none",
                "horizontal_spacing": "8px",
                "columns": [
                    {
                        "tag": "column",
                        "width": "150px",
                        "vertical_align": "center",
                        "elements": [self.app._card_label_markdown(label)],
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "vertical_align": "center",
                        "elements": [
                            {
                                "tag": "input",
                                "element_id": element_id,
                                "name": name,
                                "placeholder": {"tag": "plain_text", "content": placeholder},
                                "default_value": default_value,
                            }
                        ],
                    },
                ],
            }

        form_elements: List[dict] = [
            form_input_row(
                "Project ID *",
                element_id="project_id_input",
                name="project_id",
                placeholder="unique project id",
                default_value=project_id,
            ),
            form_input_row(
                "Working Dir *",
                element_id="project_cwd_input",
                name="cwd",
                placeholder="/root/project/...",
                default_value=cwd,
            ),
        ]
        if provider_name == "codex":
            form_elements.append(
                form_input_row(
                    "Or paste ID",
                    element_id="project_session_input",
                    name="session_id",
                    placeholder="paste an existing codex session uuid",
                    default_value=session_id,
                )
            )
            recent_session_choices = self.app._recent_codex_session_choices()
            if recent_session_choices:
                form_elements.insert(
                    len(form_elements) - 1,
                    self.app._card_select(
                        "Attach to",
                        "dm_project_set_session_id",
                        session_id,
                        recent_session_choices,
                        placeholder="Choose a recent session",
                    )[0],
                )
        form_elements.extend(
            [
                {
                    "tag": "column_set",
                    "flex_mode": "flow",
                    "horizontal_spacing": "8px",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "auto",
                            "elements": [
                                self.app._card_button(
                                    "Start",
                                    "launch_project",
                                    "primary",
                                    name="launch_project",
                                    form_action_type="submit",
                                )
                            ],
                        },
                        {
                            "tag": "column",
                            "width": "auto",
                            "elements": [
                                self.app._card_button(
                                    "Reset",
                                    "reset_project_launch",
                                    "default",
                                )
                            ],
                        },
                    ],
                },
                {
                    "tag": "column_set",
                    "horizontal_align": "right",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "auto",
                            "elements": [
                                self.app._card_button(
                                    "Back",
                                    "dm_mode_root",
                                    "default",
                                )
                            ],
                        }
                    ],
                },
            ]
        )
        elements.append(
            {
                "tag": "form",
                "element_id": "project_launch_form",
                "name": "project_launch_form",
                "vertical_spacing": "8px",
                "elements": form_elements,
            }
        )
        if notice:
            elements.append(
                {
                    "tag": "markdown",
                    "element_id": "project_launch_notice",
                    "content": f"**Notice:** {notice}",
                }
            )
        return {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "width_mode": "compact",
                "enable_forward": True,
            },
            "header": {
                "template": "orange",
                "padding": "12px 14px 10px 14px",
                "title": {"tag": "plain_text", "content": "Create Pocket Project"},
            },
            "body": {
                "padding": "14px",
                "vertical_spacing": "8px",
                "elements": elements,
            },
        }

    def project_created_card(self, project_id: str, group_chat_id: str) -> dict:
        """Build the final DM status card after a project group is created."""
        return self.success_continue_card(
            "Pocket Project Created",
            [
                f"**Project ID:** {project_id}",
                f"**Group Name:** Pocket-Project: {project_id}",
                f"**Group Chat ID:** `{group_chat_id}`",
                "",
                "The project is ready. Open the group and start chatting.",
            ],
        )

    def success_continue_card(self, title: str, lines: List[str]) -> dict:
        """Build a green success card with a continue action back to console."""
        return {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "width_mode": "compact",
                "enable_forward": True,
            },
            "header": {
                "template": "green",
                "padding": "12px 14px 10px 14px",
                "title": {"tag": "plain_text", "content": title},
            },
            "body": {
                "padding": "14px",
                "vertical_spacing": "10px",
                "elements": [
                    {
                        "tag": "markdown",
                        "element_id": "success_md",
                        "content": "\n".join(lines),
                    },
                    self.app._card_button("Continue", "dm_mode_root", "primary"),
                ],
            },
        }

    def dm_console_card(
        self,
        chat_id: str,
        *,
        mode: str = "root",
        selected_worker_id: str = "",
        dissolve_group: str = "no",
        notice: str = "",
    ) -> dict:
        """Build the DM management-console card."""
        del chat_id
        elements: List[dict] = [
            {
                "tag": "column_set",
                "horizontal_spacing": "8px",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [self.app._card_button("New", "dm_mode_project", "primary" if mode == "project" else "default")],
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [self.app._card_button("Manage", "dm_mode_status", "primary" if mode == "status" else "default")],
                    },
                ],
            }
        ]
        worker_options = self._dm_worker_options()
        if mode == "status":
            elements.extend(
                self.app._card_select(
                    "Worker",
                    "dm_status_select_worker",
                    selected_worker_id,
                    worker_options,
                    placeholder="Choose a worker",
                )
            )
            if selected_worker_id:
                elements.append(
                    {
                        "tag": "markdown",
                        "element_id": "dm_status_value",
                        "content": self._dm_worker_markdown(selected_worker_id),
                    }
                )
                if selected_worker_id.startswith("oc_"):
                    elements.append(
                        {
                            "tag": "markdown",
                            "element_id": "dm_delete_hint",
                            "content": "Type **delete** below to remove this project. You can also dissolve the group.",
                        }
                    )
                else:
                    elements.append(
                        {
                            "tag": "markdown",
                            "element_id": "dm_delete_hint",
                            "content": "Type **delete** below to remove this project.",
                        }
                    )
                if selected_worker_id.startswith("oc_"):
                    buttons: List[dict] = []
                    for label, value in [("yes", "yes"), ("no", "no")]:
                        button = self.app._card_button(
                            label,
                            "dm_status_set_dissolve",
                            "primary" if dissolve_group == value else "default",
                            selected=value,
                        )
                        button["value"]["selected_worker_id"] = selected_worker_id
                        button["behaviors"][0]["value"]["selected_worker_id"] = selected_worker_id
                        buttons.append(button)
                    elements.append(
                        self.app._card_labeled_row(
                            "Dissolve Group",
                            self.app._card_choice_columns(buttons),
                        )
                    )
                remove_button = self.app._card_button(
                    "Delete Project",
                    "dm_status_remove_confirm",
                    "default",
                    selected=selected_worker_id,
                    name="dm_status_remove_confirm",
                    form_action_type="submit",
                )
                remove_button["value"]["selected_worker_id"] = selected_worker_id
                remove_button["value"]["dissolve_group"] = dissolve_group
                remove_button["behaviors"][0]["value"]["selected_worker_id"] = selected_worker_id
                remove_button["behaviors"][0]["value"]["dissolve_group"] = dissolve_group
                elements.append(
                    {
                        "tag": "form",
                        "element_id": "dm_delete_form",
                        "name": "dm_delete_form",
                        "vertical_spacing": "8px",
                        "elements": [
                            {
                                "tag": "input",
                                "element_id": "dm_delete_confirm",
                                "name": "confirm_delete",
                                "placeholder": {"tag": "plain_text", "content": "type delete"},
                            },
                            remove_button,
                        ],
                    }
                )
        elif mode == "project":
            elements.append(
                {
                    "tag": "markdown",
                    "element_id": "dm_project_hint",
                    "content": "Use **New** to open the project-launch form.",
                }
            )
        else:
            elements.append(
                {
                    "tag": "markdown",
                    "element_id": "dm_console_hint",
                    "content": "Use this console to create or manage project workers.",
                }
            )
        if notice:
            elements.append(
                {
                    "tag": "markdown",
                    "element_id": "dm_console_notice",
                    "content": f"**Notice:** {notice}",
                }
            )
        return {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "width_mode": "compact",
                "enable_forward": True,
            },
            "header": {
                "template": "orange",
                "padding": "12px 14px 10px 14px",
                "title": {"tag": "plain_text", "content": "PoCo Console"},
            },
            "body": {
                "padding": "14px",
                "vertical_spacing": "8px",
                "elements": elements,
            },
        }

    @staticmethod
    def status_card(title: str, body: str, *, template: str = "red") -> dict:
        return {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "width_mode": "fill",
                "enable_forward": True,
            },
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": title},
            },
            "body": {
                "padding": "14px",
                "vertical_spacing": "8px",
                "elements": [
                    {
                        "tag": "markdown",
                        "element_id": "status_md",
                        "content": body,
                    }
                ],
            },
        }

    @staticmethod
    def inactive_dm_card() -> dict:
        """Render a read-only card after a newer DM control card is sent."""
        return {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "width_mode": "compact",
                "enable_forward": True,
            },
            "header": {
                "template": "grey",
                "padding": "12px 14px 10px 14px",
                "title": {"tag": "plain_text", "content": "PoCo Console"},
            },
            "body": {
                "padding": "14px",
                "vertical_spacing": "8px",
                "elements": [
                    {
                        "tag": "markdown",
                        "element_id": "dm_inactive_md",
                        "content": "This card has been replaced by a newer DM control card.",
                    }
                ],
            },
        }

    def send_setup_card(self, chat_id: str, worker_id: str, *, notice: str = "") -> None:
        ok = self.app._safe_send_card(chat_id, self.setup_card(chat_id, worker_id, notice=notice))
        if not ok:
            self.app._safe_send(chat_id, self.app._card_permission_required_text())

    def send_project_launch_card(self, chat_id: str, *, notice: str = "") -> None:
        """Send the DM project-launch card."""
        ok = self.app._safe_send_dm_card(chat_id, self.project_launch_card(chat_id, notice=notice))
        if not ok:
            self.app._safe_send(chat_id, self.app._card_permission_required_text())

    def send_dm_console_card(self, chat_id: str, *, mode: str = "root", notice: str = "") -> None:
        """Send the DM management-console card."""
        ok = self.app._safe_send_dm_card(chat_id, self.dm_console_card(chat_id, mode=mode, notice=notice))
        if not ok:
            self.app._safe_send(chat_id, self.app._card_permission_required_text())

    @staticmethod
    def response_card(card: dict, notice: str = "", toast_type: str = "info") -> P2CardActionTriggerResponse:
        payload: dict = {
            "card": {"type": "raw", "data": card},
        }
        if notice:
            payload["toast"] = {"type": toast_type, "content": notice}
        return P2CardActionTriggerResponse(payload)

    @staticmethod
    def coerce_form_value(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            for item in value:
                coerced = SetupCardController.coerce_form_value(item)
                if coerced:
                    return coerced
            return ""
        if isinstance(value, dict):
            for key in ("value", "text", "content", "key"):
                if key in value:
                    coerced = SetupCardController.coerce_form_value(value[key])
                    if coerced:
                        return coerced
        return str(value).strip()

    @staticmethod
    def action_selected_value(action) -> str:
        if action is None:
            return ""
        for attr in ("option", "input_value", "name"):
            value = getattr(action, attr, None)
            coerced = SetupCardController.coerce_form_value(value)
            if coerced:
                return coerced
        if isinstance(getattr(action, "options", None), list):
            coerced = SetupCardController.coerce_form_value(getattr(action, "options"))
            if coerced:
                return coerced
        value = action.value if isinstance(getattr(action, "value", None), dict) else {}
        for key in ("selected", "option", "value"):
            coerced = SetupCardController.coerce_form_value(value.get(key))
            if coerced:
                return coerced
        return ""

    def enable_worker(self, worker_id: str) -> Optional[str]:
        provider_name = self.app._provider_name_for_worker(worker_id)
        if not provider_name:
            return "Please select an agent first."
        if provider_name == "claude":
            backend_name, backend_error = self.app._claude_backend_status(worker_id)
            if backend_error:
                return backend_error or f"Claude backend {backend_name} is not ready."
        cwd = self.app._worker_store.cwd_for(worker_id)
        if not cwd:
            return "Please fill in the working directory first."
        validation_error = self.app._validate_cwd(cwd)
        if validation_error:
            return f"Invalid cwd: {validation_error}"
        effective_model = self.app._effective_model_for_worker(worker_id)
        if not effective_model:
            return "Please select a model first."
        self.app._worker_store.set_enabled(worker_id, True)
        return None

    def reset_worker_config(self, worker_id: str) -> None:
        self.app._store.clear(worker_id)
        self.app._worker_store.remove(worker_id)
        self.app._worker_store.ensure_worker(worker_id)

    def on_card_action_trigger(self, data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        try:
            event = data.event
            if event is None or event.context is None:
                self.app.LOG.error("Received invalid card action: missing event/context")
                return self.response_card(self.status_card("PoCo Error", "Invalid card action."), "Invalid card action.", "error")
            chat_id = str(event.context.open_chat_id or "").strip()
            if not chat_id:
                self.app.LOG.error("Received invalid card action: missing chat id")
                return self.response_card(self.status_card("PoCo Error", "Missing chat id."), "Missing chat id.", "error")
            worker_id = chat_id
            self.app._worker_store.ensure_worker(worker_id)
            action = event.action
            action_value = action.value if action is not None and isinstance(action.value, dict) else {}
            action_name = str(action_value.get("action", "")).strip()
            form_value = action.form_value if action is not None and isinstance(action.form_value, dict) else {}

            def dm_console_response(
                *,
                mode: str = "root",
                selected_worker_id: str = "",
                dissolve_group: str = "no",
                notice: str = "",
                toast_type: str = "info",
            ) -> P2CardActionTriggerResponse:
                return self.response_card(
                    self.dm_console_card(
                        chat_id,
                        mode=mode,
                        selected_worker_id=selected_worker_id,
                        dissolve_group=dissolve_group,
                        notice=notice,
                    ),
                    notice,
                    toast_type,
                )

            if action_name in {
                "dm_mode_root",
                "dm_mode_project",
                "dm_mode_status",
                "dm_project_set_provider",
                "dm_project_set_backend",
                "dm_project_set_model",
                "dm_project_set_mode",
                "dm_project_set_session_id",
                "dm_status_select_worker",
                "dm_status_set_dissolve",
                "dm_status_remove_confirm",
            }:
                if action_name == "dm_mode_root":
                    return dm_console_response(mode="root")
                if action_name == "dm_mode_project":
                    return self.response_card(self.project_launch_card(chat_id), "", "info")
                if action_name == "dm_mode_status":
                    return dm_console_response(mode="status")
                if action_name == "dm_project_set_provider":
                    selected = self.action_selected_value(action)
                    if not selected:
                        return self.response_card(self.project_launch_card(chat_id, notice="Choose an agent first."), "Choose an agent first.", "error")
                    updates = {"provider": selected}
                    if selected == "codex":
                        updates["backend"] = "openai"
                        updates["model"] = "gpt-5.4"
                    else:
                        backend = self.app._config.claude_default_backend.strip().lower() or "anthropic"
                        updates["backend"] = backend
                        payload = self.app._config.claude_backends.get(backend, {})
                        updates["model"] = str(payload.get("default_model", "")).strip() if isinstance(payload, dict) else ""
                    self.app._merge_project_draft(chat_id, **updates)
                    return self.response_card(self.project_launch_card(chat_id), "", "success")
                if action_name == "dm_project_set_backend":
                    selected = self.action_selected_value(action)
                    if not selected:
                        return self.response_card(self.project_launch_card(chat_id, notice="Choose a provider first."), "Choose a provider first.", "error")
                    payload = self.app._config.claude_backends.get(selected, {})
                    model = str(payload.get("default_model", "")).strip() if isinstance(payload, dict) else ""
                    self.app._merge_project_draft(chat_id, backend=selected, model=model)
                    return self.response_card(self.project_launch_card(chat_id), "", "success")
                if action_name == "dm_project_set_model":
                    selected = self.action_selected_value(action)
                    if not selected:
                        return self.response_card(self.project_launch_card(chat_id, notice="Choose a model first."), "Choose a model first.", "error")
                    self.app._merge_project_draft(chat_id, model=selected)
                    return self.response_card(self.project_launch_card(chat_id), "", "success")
                if action_name == "dm_project_set_mode":
                    selected = self.action_selected_value(action)
                    if not selected:
                        return self.response_card(self.project_launch_card(chat_id, notice="Choose a reply mode first."), "Choose a reply mode first.", "error")
                    self.app._merge_project_draft(chat_id, mode=selected)
                    return self.response_card(self.project_launch_card(chat_id), "", "success")
                if action_name == "dm_project_set_session_id":
                    selected = self.action_selected_value(action)
                    if not selected:
                        return self.response_card(self.project_launch_card(chat_id, notice="Choose a session first."), "Choose a session first.", "error")
                    self.app._merge_project_draft(chat_id, session_id=selected)
                    return self.response_card(self.project_launch_card(chat_id), "", "success")
                if action_name == "dm_status_select_worker":
                    selected = self.action_selected_value(action)
                    if not selected:
                        return dm_console_response(mode="status", notice="Choose a worker first.", toast_type="error")
                    return dm_console_response(mode="status", selected_worker_id=selected)
                if action_name == "dm_status_set_dissolve":
                    selected = self.action_selected_value(action)
                    current_worker_id = str(action_value.get("selected_worker_id", "")).strip()
                    if not current_worker_id:
                        current_worker_id = str(action_value.get("worker_id", "")).strip()
                    return dm_console_response(
                        mode="status",
                        selected_worker_id=current_worker_id,
                        dissolve_group=selected or "no",
                    )
                if action_name == "dm_status_remove_confirm":
                    worker_id = str(action_value.get("selected_worker_id", "")).strip() or self.action_selected_value(action) or str(action_value.get("selected", "")).strip()
                    if not worker_id:
                        return dm_console_response(mode="status", notice="Choose a worker first.", toast_type="error")
                    confirm_delete = self.coerce_form_value(form_value.get("confirm_delete")).lower()
                    if confirm_delete != "delete":
                        return dm_console_response(
                            mode="status",
                            selected_worker_id=worker_id,
                            dissolve_group=str(action_value.get("dissolve_group", "no")).strip().lower(),
                            notice="Type delete to confirm removal.",
                            toast_type="error",
                        )
                    dissolve_group = str(action_value.get("dissolve_group", "no")).strip().lower()
                    if worker_id.startswith("oc_") and dissolve_group == "yes":
                        try:
                            self.app._messenger.delete_chat(worker_id)
                        except Exception as exc:
                            return dm_console_response(
                                mode="status",
                                selected_worker_id=worker_id,
                                dissolve_group=dissolve_group,
                                notice=f"Failed to dissolve group: {exc}",
                                toast_type="error",
                            )
                    try:
                        self.app._remove_worker(worker_id)
                    except Exception as exc:
                        return dm_console_response(
                            mode="status",
                            selected_worker_id=worker_id,
                            dissolve_group=dissolve_group,
                            notice=str(exc),
                            toast_type="error",
                        )
                    return self.response_card(
                        self.success_continue_card(
                            "Project Removed",
                            [
                                f"**Worker:** `{worker_id}`",
                                "",
                                "The project record has been removed.",
                            ],
                        ),
                        "Removed.",
                        "success",
                    )

            if action_name in {"launch_project", "reset_project_launch"}:
                def project_card_response(
                    notice: str = "",
                    toast_type: str = "info",
                    *,
                    form_project_id: str = "",
                    form_cwd: str = "",
                    form_session_id: str = "",
                ) -> P2CardActionTriggerResponse:
                    return self.response_card(
                        self.project_launch_card(
                            chat_id,
                            notice=notice,
                            form_project_id=form_project_id,
                            form_cwd=form_cwd,
                            form_session_id=form_session_id,
                        ),
                        notice,
                        toast_type,
                    )

                if action_name == "reset_project_launch":
                    self.app._reset_project_draft(chat_id)
                    return project_card_response("Reset.", "success")

                project_id = self.coerce_form_value(form_value.get("project_id"))
                cwd = self.coerce_form_value(form_value.get("cwd"))
                session_id = self.coerce_form_value(form_value.get("session_id"))
                draft = self.app._merge_project_draft(chat_id, project_id=project_id, cwd=cwd, session_id=session_id)
                normalized_project_id = self.app._normalize_alias(project_id)
                if normalized_project_id is None:
                    return project_card_response(
                        "Project ID is invalid. Use lowercase letters, digits, '-' and '_'.",
                        "error",
                        form_project_id=project_id,
                        form_cwd=cwd,
                        form_session_id=session_id,
                    )
                if self.app._worker_store.alias_in_use(normalized_project_id):
                    return project_card_response(
                        f"Project ID `{normalized_project_id}` is already in use.",
                        "error",
                        form_project_id=project_id,
                        form_cwd=cwd,
                        form_session_id=session_id,
                    )
                if not cwd:
                    return project_card_response(
                        "Please fill in Working Dir first.",
                        "error",
                        form_project_id=project_id,
                        form_cwd=cwd,
                        form_session_id=session_id,
                    )
                validation_error = self.app._validate_cwd(cwd)
                if validation_error:
                    return project_card_response(
                        f"Invalid Working Dir: {validation_error}",
                        "error",
                        form_project_id=project_id,
                        form_cwd=cwd,
                        form_session_id=session_id,
                    )
                if session_id:
                    if str(draft.get("provider", "")).strip().lower() != "codex":
                        return project_card_response(
                            "Attach session is only available for Codex.",
                            "error",
                            form_project_id=project_id,
                            form_cwd=cwd,
                            form_session_id=session_id,
                        )
                    try:
                        import uuid as _uuid

                        _uuid.UUID(session_id.strip())
                    except ValueError:
                        return project_card_response(
                            "Existing Session ID must be a valid UUID.",
                            "error",
                            form_project_id=project_id,
                            form_cwd=cwd,
                            form_session_id=session_id,
                        )
                requester_open_id = str(getattr(getattr(event, "operator", None), "open_id", "") or "").strip()
                if not requester_open_id:
                    return project_card_response(
                        "Missing requester open_id from card callback.",
                        "error",
                        form_project_id=project_id,
                        form_cwd=cwd,
                        form_session_id=session_id,
                    )
                group_chat_id = self.app._create_project_group_from_dm(
                    chat_id,
                    requester_open_id,
                    normalized_project_id,
                    cwd,
                    provider_name=str(draft.get("provider", "codex")),
                    backend=str(draft.get("backend", "openai")),
                    model=str(draft.get("model", "gpt-5.4")),
                    mode=str(draft.get("mode", "auto")),
                    attach_session_id=session_id.strip(),
                )
                return self.response_card(
                    self.project_created_card(normalized_project_id, group_chat_id),
                    "Project created.",
                    "success",
                )

            def current_card(
                notice: str = "",
                toast_type: str = "info",
                *,
                form_alias: str = "",
                form_cwd: str = "",
                read_only: bool = False,
            ) -> P2CardActionTriggerResponse:
                return self.response_card(
                    self.setup_card(
                        chat_id,
                        worker_id,
                        notice=notice,
                        form_alias=form_alias,
                        form_cwd=form_cwd,
                        read_only=read_only,
                    ),
                    notice,
                    toast_type,
                )

            if action_name == "save_setup":
                alias = self.coerce_form_value(form_value.get("alias"))
                cwd = self.coerce_form_value(form_value.get("cwd"))
                if alias:
                    normalized_alias = self.app._normalize_alias(alias)
                    if normalized_alias is None:
                        return current_card(
                            "Project ID is invalid. Use lowercase letters, digits, '-' and '_'.",
                            "error",
                            form_alias=alias,
                            form_cwd=cwd,
                        )
                    try:
                        self.app._worker_store.set_alias(worker_id, normalized_alias)
                    except ValueError as exc:
                        return current_card(str(exc), "error", form_alias=alias, form_cwd=cwd)
                if cwd:
                    validation_error = self.app._validate_cwd(cwd)
                    if validation_error:
                        return current_card(
                            f"Invalid cwd: {validation_error}",
                            "error",
                            form_alias=alias,
                            form_cwd=cwd,
                        )
                    self.app._worker_store.set_cwd(worker_id, cwd)
                return current_card("Draft saved.")
            if action_name == "enable_setup":
                alias = self.coerce_form_value(form_value.get("alias"))
                cwd = self.coerce_form_value(form_value.get("cwd"))
                current_cwd = self.app._worker_store.cwd_for(worker_id)
                if alias:
                    normalized_alias = self.app._normalize_alias(alias)
                    if normalized_alias is None:
                        return current_card(
                            "Project ID is invalid. Use lowercase letters, digits, '-' and '_'.",
                            "error",
                            form_alias=alias,
                            form_cwd=cwd,
                        )
                    try:
                        self.app._worker_store.set_alias(worker_id, normalized_alias)
                    except ValueError as exc:
                        return current_card(str(exc), "error", form_alias=alias, form_cwd=cwd)
                if cwd:
                    validation_error = self.app._validate_cwd(cwd)
                    if validation_error:
                        return current_card(
                            f"Invalid cwd: {validation_error}",
                            "error",
                            form_alias=alias,
                            form_cwd=cwd,
                        )
                    if cwd != current_cwd:
                        recycle_error = self.app._recycle_worker_runtime(
                            worker_id,
                            reason="Stop the current reply before changing Working Dir.",
                        )
                        if recycle_error:
                            return current_card(
                                recycle_error,
                                "error",
                                form_alias=alias,
                                form_cwd=cwd,
                            )
                    self.app._worker_store.set_cwd(worker_id, cwd)
                enable_error = self.enable_worker(worker_id)
                if enable_error:
                    self.app.LOG.warning("Card action enable_setup rejected for worker_id=%s: %s", worker_id, enable_error)
                    return current_card(enable_error, "error", form_alias=alias, form_cwd=cwd)
                return current_card(read_only=True)
            if action_name == "reset_session":
                self.app._store.clear(worker_id)
                return current_card("Started a fresh chat.")
            if action_name == "reset_config":
                self.reset_worker_config(worker_id)
                return current_card("Reset.", "success")
            if action_name == "test_ping":
                return self.response_card(self.minimal_test_card("pong"), "pong", "success")
            if action_name in {"set_provider", "set_backend", "set_model", "set_mode"}:
                selected = self.action_selected_value(action)
                if not selected:
                    self.app.LOG.warning("Card action %s missing selected value for worker_id=%s", action_name, worker_id)
                    return current_card("No selection received.", "error")
                if action_name == "set_provider":
                    current_provider = self.app._provider_name_for_worker(worker_id)
                    if selected != current_provider:
                        recycle_error = self.app._recycle_worker_runtime(
                            worker_id,
                            reason="Stop the current reply before changing Agent.",
                        )
                        if recycle_error:
                            return current_card(recycle_error, "error")
                    self.app._worker_store.set_provider(worker_id, selected)
                    if selected == "codex":
                        self.app._worker_store.set_backend(worker_id, "openai")
                    elif selected == "claude":
                        self.app._worker_store.set_backend(worker_id, self.app._claude_backend_name(worker_id))
                    return current_card(f"Agent set to {selected}.")
                if action_name == "set_backend":
                    current_backend = self.app._worker_store.backend_for(worker_id)
                    if selected != current_backend:
                        recycle_error = self.app._recycle_worker_runtime(
                            worker_id,
                            reason="Stop the current reply before changing Provider.",
                        )
                        if recycle_error:
                            return current_card(recycle_error, "error")
                    self.app._worker_store.set_backend(worker_id, selected)
                    return current_card(f"Provider set to {selected}.")
                if action_name == "set_model":
                    current_model = self.app._effective_model_for_worker(worker_id)
                    if selected != current_model:
                        recycle_error = self.app._recycle_worker_runtime(
                            worker_id,
                            reason="Stop the current reply before changing Model.",
                        )
                        if recycle_error:
                            return current_card(recycle_error, "error")
                    self.app._worker_store.set_model(worker_id, selected)
                    return current_card(f"Model set to {selected}.")
                if action_name == "set_mode":
                    self.app._worker_store.set_mode(worker_id, selected)
                    return current_card(f"Reply mode set to {self.app._reply_mode_label(selected)}.")
            self.app.LOG.warning("Card action unsupported for worker_id=%s action=%s", worker_id, action_name or "(empty)")
            return current_card("Unsupported action.", "error")
        except Exception:
            self.app.LOG.exception("Unhandled card action trigger failure")
            return self.response_card(
                self.status_card("PoCo Error", "**PoCo** encountered a local error. Please check local logs."),
                "Local card handler error. Check PoCo logs.",
                "error",
            )

    @staticmethod
    def group_help_text() -> str:
        return (
            "[poco] 这是项目工作区。\n"
            "群里的配置、重置、删除等生命周期操作都在 DM 控制台完成。\n"
            "在这里直接聊天即可，PoCo 会把消息转给当前 agent。\n"
            "图片输入：请把图片和文字说明放在同一条飞书图文消息里发送。\n"
            "如果需要创建、删除、重置项目或查看状态，请回到 DM 控制台发送 `poco`。"
        )

    @staticmethod
    def dm_help_text() -> str:
        return (
            "[poco] 这是单聊管理控制台。\n"
            "直接发送 `poco` 即可打开控制台卡片。\n"
            "在控制台里完成新建项目、查看状态、删除项目。\n"
            "把 bot 拉进项目群后，在群里直接聊天即可。"
        )

    def _dm_worker_options(self) -> List[tuple[str, str]]:
        """Return worker select options for the DM console."""
        options: List[tuple[str, str]] = []
        for worker_id, alias in self.app._worker_store.items():
            label = alias or worker_id
            if alias:
                label = f"{alias} · {worker_id}"
            options.append((label, worker_id))
        return options

    def _dm_worker_markdown(self, worker_id: str) -> str:
        """Render one worker summary as markdown for the DM console."""
        alias = self.app._worker_store.alias_for(worker_id) or "-"
        provider_name = self.app._provider_name_for_worker(worker_id) or "(unset)"
        backend = self.app._worker_store.backend_for(worker_id) or "(n/a)"
        model = self.app._effective_model_for_worker(worker_id) or "(unset)"
        mode = self.app._reply_mode_label(self.app._worker_store.mode_for(worker_id))
        cwd = self.app._worker_store.cwd_for(worker_id) or "(unset)"
        enabled = "true" if self.app._worker_store.enabled_for(worker_id) else "false"
        return "\n".join(
            [
                f"**Worker:** {alias}",
                f"**Chat ID:** `{worker_id}`",
                f"**Agent:** {provider_name}",
                f"**Provider:** {backend}",
                f"**Model:** {model}",
                f"**Reply Mode:** {mode}",
                f"**Working Dir:** `{cwd}`",
                f"**Enabled:** {enabled}",
            ]
        )
