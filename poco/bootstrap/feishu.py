"""Feishu self-built app bootstrap helpers."""

from __future__ import annotations

import getpass
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Set

import lark_oapi as lark
import requests
from lark_oapi.api.application.v6 import (
    ApplyScopeRequest,
    AppScope,
    Application,
    Callback,
    GetApplicationRequest,
    ListScopeRequest,
    PatchApplicationRequest,
    SubscribedEvent,
)

from ..config import ConfigStore, bind_workspace, build_paths, ensure_dirs, get_nested, normalize_config_key, set_nested, workspace_binding

BASE_URL = "https://open.feishu.cn/open-apis"
REQUIRED_SCOPES = [
    "cardkit:card:write",
    "im:chat",
    "im:chat:operate_as_owner",
    "im:message.group_at_msg:readonly",
    "im:message.group_msg:readonly",
    "im:message.p2p_msg:readonly",
    "im:message:send_as_bot",
]
REQUIRED_EVENTS = [
    "im.message.receive_v1",
]
REQUIRED_CALLBACKS = [
    "card.action.trigger",
]


@dataclass(slots=True)
class CurrentAppState:
    """Snapshot of the current Feishu app configuration."""

    scopes: Set[str] = field(default_factory=set)
    event_subscription_type: str = ""
    events: Set[str] = field(default_factory=set)
    callback_subscription_type: str = ""
    callbacks: Set[str] = field(default_factory=set)


class FeishuBootstrapper:
    """Applies PoCo's desired configuration to one Feishu app."""

    def __init__(self, app_id: str, app_secret: str, store: ConfigStore) -> None:
        self.app_id = app_id.strip()
        self.app_secret = app_secret.strip()
        self._store = store
        self._http = requests.Session()
        self._client = (
            lark.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

    def validate_credentials(self) -> str:
        """Fetch a tenant token to validate APP ID / APP Secret."""
        response = self._http.post(
            f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code", 0) != 0:
            raise RuntimeError(
                f"Feishu auth failed: code={payload.get('code')}, msg={payload.get('msg', '')}"
            )
        token = str(payload.get("tenant_access_token", "")).strip()
        if not token:
            raise RuntimeError("Feishu auth succeeded but returned no tenant_access_token.")
        return token

    def save_local_credentials(self) -> None:
        """Persist APP ID / APP Secret into PoCo's local config."""
        config = self._store.load()
        set_nested(config, normalize_config_key("app_id"), self.app_id)
        set_nested(config, normalize_config_key("app_secret"), self.app_secret)
        self._store.save(config)

    def fetch_current_state(self) -> CurrentAppState:
        """Read the app's current scopes, events and callbacks."""
        request = (
            GetApplicationRequest.builder()
            .app_id(self.app_id)
            .lang("en_us")
            .build()
        )
        response = self._client.application.v6.application.get(request)
        if response.code != 0:
            raise RuntimeError(
                f"Feishu app read failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )
        app = response.data.app if response.data is not None else None

        scope_request = ListScopeRequest.builder().build()
        scope_response = self._client.application.v6.scope.list(scope_request)
        if scope_response.code != 0:
            raise RuntimeError(
                f"Feishu scope list failed: code={scope_response.code}, msg={scope_response.msg}, "
                f"log_id={scope_response.get_log_id()}"
            )
        listed_scopes = {
            str(item.scope_name).strip()
            for item in (scope_response.data.scopes if scope_response.data is not None else [])
            if str(item.scope_name).strip()
        }
        app_scopes = {
            str(item.scope).strip()
            for item in (app.scopes if app is not None and app.scopes is not None else [])
            if str(item.scope).strip()
        }
        event = app.event if app is not None else None
        callback = app.callback if app is not None else None
        return CurrentAppState(
            scopes=listed_scopes or app_scopes,
            event_subscription_type=str(getattr(event, "subscription_type", "") or "").strip(),
            events={
                str(item).strip()
                for item in (getattr(event, "subscribed_events", None) or [])
                if str(item).strip()
            },
            callback_subscription_type=str(getattr(callback, "callback_type", "") or "").strip(),
            callbacks={
                str(item).strip()
                for item in (getattr(callback, "subscribed_callbacks", None) or [])
                if str(item).strip()
            },
        )

    def conflict_warnings(self, current: CurrentAppState) -> List[str]:
        """Generate warnings for settings that will be overwritten."""
        warnings: List[str] = []
        desired_scopes = set(REQUIRED_SCOPES)
        extra_scopes = sorted(current.scopes - desired_scopes)
        missing_scopes = sorted(desired_scopes - current.scopes)
        if extra_scopes:
            warnings.append(
                "Existing scopes will be overwritten. Extra scopes currently present: "
                + ", ".join(extra_scopes)
            )
        if missing_scopes:
            warnings.append("Missing required scopes: " + ", ".join(missing_scopes))
        if current.event_subscription_type and current.event_subscription_type != "websocket":
            warnings.append(
                "Event subscription type will be rewritten to websocket "
                f"(current: {current.event_subscription_type})."
            )
        if current.events != set(REQUIRED_EVENTS):
            warnings.append(
                "Event subscriptions will be rewritten "
                f"(current: {', '.join(sorted(current.events)) or '(none)'})."
            )
        if current.callback_subscription_type and current.callback_subscription_type != "websocket":
            warnings.append(
                "Callback subscription type will be rewritten to websocket "
                f"(current: {current.callback_subscription_type})."
            )
        if current.callbacks != set(REQUIRED_CALLBACKS):
            warnings.append(
                "Callback subscriptions will be rewritten "
                f"(current: {', '.join(sorted(current.callbacks)) or '(none)'})."
            )
        return warnings

    def apply_desired_state(self) -> None:
        """Patch scopes, events and callbacks to PoCo's required state."""
        request = (
            PatchApplicationRequest.builder()
            .app_id(self.app_id)
            .lang("en_us")
            .request_body(
                Application.builder()
                .scopes([AppScope.builder().scope(scope).build() for scope in REQUIRED_SCOPES])
                .event(
                    SubscribedEvent.builder()
                    .subscription_type("websocket")
                    .subscribed_events(REQUIRED_EVENTS)
                    .build()
                )
                .callback(
                    Callback.builder()
                    .callback_type("websocket")
                    .subscribed_callbacks(REQUIRED_CALLBACKS)
                    .build()
                )
                .build()
            )
            .build()
        )
        response = self._client.application.v6.application.patch(request)
        if response.code != 0:
            if response.code == 99991672:
                raise RuntimeError(
                    "Feishu app patch failed: this app still needs one manual app-management "
                    "permission in Feishu Open Platform. Grant either "
                    "`application:application` or `admin:app.category:update`, then rerun "
                    f"bootstrap. log_id={response.get_log_id()}"
                )
            raise RuntimeError(
                f"Feishu app patch failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )

    def apply_scopes(self) -> None:
        """Submit the scope application request."""
        response = self._client.application.v6.scope.apply(ApplyScopeRequest.builder().build())
        if response.code != 0:
            if response.code == 212002:
                return
            raise RuntimeError(
                f"Feishu scope apply failed: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )


def _prompt_with_default(prompt: str, default: str, *, secret: bool = False) -> str:
    """Prompts for one value, keeping the existing default on empty input."""
    suffix = " [saved]" if secret and default else f" [{default}]" if default else ""
    full_prompt = f"{prompt}{suffix}: "
    reader: Callable[[str], str] = getpass.getpass if secret else input
    value = reader(full_prompt).strip()
    return value or default


def run_feishu_bootstrap_cli(workspace: Path) -> int:
    """Runs Feishu bootstrap as a simple two-step CLI wizard."""
    bound_app_id = workspace_binding(workspace)
    draft_store = ConfigStore(build_paths(bound_app_id or "default").config_path, build_paths(bound_app_id or "default"))
    config = draft_store.load()
    draft_app_id = str(get_nested(config, "feishu.app_id") or "").strip()
    draft_app_secret = str(get_nested(config, "feishu.app_secret") or "").strip()

    print("PoCo Feishu Bootstrap")
    print()
    print("Step 1 of 2. Enter APP ID.")
    app_id = _prompt_with_default("APP ID", draft_app_id)
    if not app_id:
        print("ERROR  APP ID is required.")
        return 1

    print()
    print("Step 2 of 2. Enter APP Secret.")
    app_secret = _prompt_with_default("APP Secret", draft_app_secret, secret=True)
    if not app_secret:
        print("ERROR  APP Secret is required.")
        return 1

    bound_paths = build_paths(app_id)
    ensure_dirs(bound_paths)
    store = ConfigStore(bound_paths.config_path, bound_paths)
    bootstrapper = FeishuBootstrapper(app_id, app_secret, store)
    try:
        print("INFO   Starting Feishu bootstrap.")
        print("INFO   Validating APP ID / APP Secret.")
        bootstrapper.validate_credentials()
        print("OK     Credentials are valid.")

        print("INFO   Saving local PoCo config.")
        bootstrapper.save_local_credentials()
        bind_workspace(workspace, app_id)
        print(f"OK     Bound workspace `{workspace}` to `{app_id}`.")
        print(f"OK     Saved APP ID / APP Secret into {bound_paths.config_path}.")

        print("INFO   Reading current Feishu app state.")
        current = bootstrapper.fetch_current_state()
        warnings = bootstrapper.conflict_warnings(current)
        if warnings:
            for warning in warnings:
                print(f"WARNING {warning}")
        else:
            print("OK     Current Feishu app state already matches PoCo's target shape.")

        print("INFO   Rewriting scopes, events and callbacks.")
        bootstrapper.apply_desired_state()
        print("OK     Feishu app config patched.")

        print("INFO   Applying scopes.")
        bootstrapper.apply_scopes()
        print("OK     Scope application submitted.")

        print("INFO   Bootstrap completed. Create and publish the new app version manually in Feishu Open Platform.")

        print("FINISH PoCo bootstrap finished.")
        return 0
    except Exception as exc:
        print(f"ERROR  {exc}")
        return 1
