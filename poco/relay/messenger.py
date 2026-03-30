"""Feishu API wrapper used by the relay runtime."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Dict, Optional

import lark_oapi as lark
from lark_oapi.api.cardkit.v1.model.content_card_element_request import ContentCardElementRequest
from lark_oapi.api.cardkit.v1.model.content_card_element_request_body import ContentCardElementRequestBody
from lark_oapi.api.cardkit.v1.model.create_card_request import CreateCardRequest
from lark_oapi.api.cardkit.v1.model.create_card_request_body import CreateCardRequestBody
from lark_oapi.api.cardkit.v1.model.settings_card_request import SettingsCardRequest
from lark_oapi.api.cardkit.v1.model.settings_card_request_body import SettingsCardRequestBody
from lark_oapi.api.im.v1 import (
    CreateChatMembersRequest,
    CreateChatMembersRequestBody,
    CreateChatRequest,
    CreateChatRequestBody,
    CreateMessageRequest,
    CreateMessageRequestBody,
    DeleteChatRequest,
    GetImageRequest,
    GetMessageResourceRequest,
    UpdateMessageRequest,
    UpdateMessageRequestBody,
)

from .models import AppConfig, SentMessage
from .utils import chunk_text


class FeishuMessenger:
    """Wraps the Feishu SDK with bridge-oriented helpers."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._client = (
            lark.Client.builder()
            .app_id(config.feishu_app_id)
            .app_secret(config.feishu_app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

    def create_text(self, chat_id: str, text: str) -> SentMessage:
        first_sent: Optional[SentMessage] = None
        for chunk in chunk_text(text, self._config.message_limit):
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(json.dumps({"text": chunk}, ensure_ascii=False))
                    .uuid(str(uuid.uuid4()))
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if response.code != 0:
                raise RuntimeError(
                    f"Feishu send failed: code={response.code}, msg={response.msg}, "
                    f"log_id={response.get_log_id()}"
                )
            if first_sent is None:
                message_id = response.data.message_id if response.data is not None else None
                if not message_id:
                    raise RuntimeError("Feishu send succeeded but returned no message_id")
                first_sent = SentMessage(message_id=message_id, chat_id=chat_id)
        assert first_sent is not None
        return first_sent

    def send_text(self, chat_id: str, text: str) -> None:
        self.create_text(chat_id, text)

    def create_card(self, chat_id: str, card: dict) -> SentMessage:
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(json.dumps(card, ensure_ascii=False))
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.create(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu send card failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )
        message_id = response.data.message_id if response.data is not None else None
        if not message_id:
            raise RuntimeError("Feishu card send succeeded but returned no message_id")
        return SentMessage(message_id=message_id, chat_id=chat_id)

    def create_template_card(
        self,
        chat_id: str,
        template_id: str,
        template_variable: Optional[dict] = None,
        template_version_name: str = "",
    ) -> SentMessage:
        data: dict = {"template_id": template_id}
        if template_version_name:
            data["template_version_name"] = template_version_name
        if template_variable:
            data["template_variable"] = template_variable
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(json.dumps({"type": "template", "data": data}, ensure_ascii=False))
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.create(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu send template card failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )
        message_id = response.data.message_id if response.data is not None else None
        if not message_id:
            raise RuntimeError("Feishu template card send succeeded but returned no message_id")
        return SentMessage(message_id=message_id, chat_id=chat_id)

    def create_card_entity(self, card: dict) -> str:
        request = (
            CreateCardRequest.builder()
            .request_body(
                CreateCardRequestBody.builder()
                .type("card_json")
                .data(json.dumps(card, ensure_ascii=False, separators=(",", ":")))
                .build()
            )
            .build()
        )
        response = self._client.cardkit.v1.card.create(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu create card entity failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )
        card_id = response.data.card_id if response.data is not None else None
        if not card_id:
            raise RuntimeError("Feishu card entity create succeeded but returned no card_id")
        return card_id

    def create_card_entity_message(self, chat_id: str, card_id: str) -> SentMessage:
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(json.dumps({"type": "card", "data": {"card_id": card_id}}, ensure_ascii=False))
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.create(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu send card entity failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )
        message_id = response.data.message_id if response.data is not None else None
        if not message_id:
            raise RuntimeError("Feishu card entity send succeeded but returned no message_id")
        return SentMessage(message_id=message_id, chat_id=chat_id)

    def create_project_group(self, project_id: str, user_open_id: str) -> str:
        """Create a private project group and seed it with the user and bot.

        The happy path uses the documented chat-create request body fields
        exposed by the Feishu SDK (`user_id_list` and `bot_id_list`). If the
        tenant rejects that combined request, PoCo falls back to:

        1. create an empty private group
        2. add the requesting user by `open_id`
        3. add the current bot by `app_id`
        """

        group_name = f"Pocket-Project: {project_id}"
        description = f"PoCo project workspace for {project_id}"
        body = (
            CreateChatRequestBody.builder()
            .name(group_name)
            .description(description)
            .chat_mode("group")
            .chat_type("private")
            .external(False)
            .join_message_visibility("all_members")
            .leave_message_visibility("all_members")
            .membership_approval("no_approval_required")
            .user_id_list([user_open_id])
            .bot_id_list([self._config.feishu_app_id])
            .build()
        )
        request = (
            CreateChatRequest.builder()
            .user_id_type("open_id")
            .set_bot_manager(False)
            .uuid(str(uuid.uuid4()))
            .request_body(body)
            .build()
        )
        response = self._client.im.v1.chat.create(request)
        if response.code == 0 and response.data is not None and response.data.chat_id:
            return str(response.data.chat_id)

        fallback_body = (
            CreateChatRequestBody.builder()
            .name(group_name)
            .description(description)
            .chat_mode("group")
            .chat_type("private")
            .external(False)
            .join_message_visibility("all_members")
            .leave_message_visibility("all_members")
            .membership_approval("no_approval_required")
            .build()
        )
        fallback_request = (
            CreateChatRequest.builder()
            .user_id_type("open_id")
            .set_bot_manager(False)
            .uuid(str(uuid.uuid4()))
            .request_body(fallback_body)
            .build()
        )
        fallback_response = self._client.im.v1.chat.create(fallback_request)
        if fallback_response.code != 0:
            raise RuntimeError(
                f"Feishu create chat failed: code={fallback_response.code}, msg={fallback_response.msg}, "
                f"log_id={fallback_response.get_log_id()}"
            )
        chat_id = str(fallback_response.data.chat_id) if fallback_response.data is not None else ""
        if not chat_id:
            raise RuntimeError("Feishu create chat succeeded but returned no chat_id")
        self.add_chat_members(chat_id, "open_id", [user_open_id])
        self.add_chat_members(chat_id, "app_id", [self._config.feishu_app_id], allow_existing=True)
        return chat_id

    def delete_chat(self, chat_id: str) -> None:
        """Dissolve a chat created/owned by the current app."""
        request = DeleteChatRequest.builder().chat_id(chat_id).build()
        response = self._client.im.v1.chat.delete(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu delete chat failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )

    def add_chat_members(
        self,
        chat_id: str,
        member_id_type: str,
        id_list: list[str],
        *,
        allow_existing: bool = False,
    ) -> None:
        ids = [item.strip() for item in id_list if item and item.strip()]
        if not ids:
            return
        request = (
            CreateChatMembersRequest.builder()
            .chat_id(chat_id)
            .member_id_type(member_id_type)
            .request_body(CreateChatMembersRequestBody.builder().id_list(ids).build())
            .build()
        )
        response = self._client.im.v1.chat_members.create(request)
        if response.code == 0:
            return
        if allow_existing:
            message = f"{response.msg}".lower()
            if "already" in message or "exist" in message or "exists" in message:
                return
        raise RuntimeError(
            f"Feishu add chat members failed: code={response.code}, msg={response.msg}, "
            f"log_id={response.get_log_id()}"
        )

    def download_image(self, image_key: str, dest_dir: Path, *, message_id: str = "") -> Path:
        if message_id:
            request = (
                GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(image_key)
                .type("image")
                .build()
            )
            response = self._client.im.v1.message_resource.get(request)
            if response.code == 0 and response.file is not None:
                return self._write_downloaded_file(response.file, response.file_name, dest_dir)
        request = GetImageRequest.builder().image_key(image_key).build()
        response = self._client.im.v1.image.get(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu download image failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )
        if response.file is None:
            raise RuntimeError("Feishu image download succeeded but returned no file stream")
        return self._write_downloaded_file(response.file, response.file_name, dest_dir)

    @staticmethod
    def _write_downloaded_file(file_obj, file_name: Optional[str], dest_dir: Path) -> Path:
        suffix = Path(file_name or "").suffix or ".bin"
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{uuid.uuid4().hex}{suffix}"
        with path.open("wb") as handle:
            shutil.copyfileobj(file_obj, handle)
        return path

    def stream_card_text(self, card_id: str, element_id: str, text: str, sequence: int) -> None:
        request = (
            ContentCardElementRequest.builder()
            .card_id(card_id)
            .element_id(element_id)
            .request_body(
                ContentCardElementRequestBody.builder()
                .uuid(str(uuid.uuid4()))
                .sequence(sequence)
                .content(text)
                .build()
            )
            .build()
        )
        response = self._client.cardkit.v1.card_element.content(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu stream card text failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )

    def set_card_streaming_mode(
        self,
        card_id: str,
        *,
        enabled: bool,
        sequence: int,
        summary: str = "",
    ) -> None:
        settings: Dict[str, object] = {"config": {"streaming_mode": enabled}}
        if summary:
            settings["config"]["summary"] = {"content": summary}
        request = (
            SettingsCardRequest.builder()
            .card_id(card_id)
            .request_body(
                SettingsCardRequestBody.builder()
                .uuid(str(uuid.uuid4()))
                .sequence(sequence)
                .settings(json.dumps(settings, ensure_ascii=False, separators=(",", ":")))
                .build()
            )
            .build()
        )
        response = self._client.cardkit.v1.card.settings(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu card settings failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )

    def update_text(self, message_id: str, text: str) -> None:
        request = (
            UpdateMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                UpdateMessageRequestBody.builder()
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.update(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu update failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )

    def update_card(self, message_id: str, card: dict) -> None:
        request = (
            UpdateMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                UpdateMessageRequestBody.builder()
                .msg_type("interactive")
                .content(json.dumps(card, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.update(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu update card failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )
