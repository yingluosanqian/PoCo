from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import os
import re
import shutil
import subprocess
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BackendConfigField:
    key: str
    label: str
    input_kind: str = "select"
    placeholder: str | None = None
    sensitive: bool = False
    options: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class BackendDescriptor:
    key: str
    label: str
    model_options: tuple[str, ...] = ()
    config_fields: tuple[BackendConfigField, ...] = ()
    default_config: dict[str, object] = field(default_factory=dict)


_BACKEND_DESCRIPTORS: dict[str, BackendDescriptor] = {
    "codex": BackendDescriptor(
        key="codex",
        label="Codex",
        config_fields=(
            BackendConfigField(
                key="sandbox",
                label="Access",
                options=(
                    ("Read Only", "read-only"),
                    ("Project Only", "workspace-write"),
                    ("Full Access", "danger-full-access"),
                ),
            ),
            BackendConfigField(
                key="reasoning_effort",
                label="Reasoning",
                options=(
                    ("Low", "low"),
                    ("Medium", "medium"),
                    ("High", "high"),
                ),
            ),
        ),
        default_config={"sandbox": "workspace-write", "reasoning_effort": "medium"},
    ),
    "claude_code": BackendDescriptor(
        key="claude_code",
        label="Claude Code",
        model_options=(
            "sonnet",
            "opus",
        ),
        config_fields=(
            BackendConfigField(
                key="permission_mode",
                label="Permission",
                options=(
                    ("Default", "default"),
                    ("Accept Edits", "acceptEdits"),
                    ("Plan", "plan"),
                    ("Bypass Permissions", "bypassPermissions"),
                ),
            ),
            BackendConfigField(
                key="anthropic_base_url",
                label="ANTHROPIC_BASE_URL",
                input_kind="text",
                placeholder="http://localhost:8765",
            ),
            BackendConfigField(
                key="anthropic_api_key",
                label="ANTHROPIC_API_KEY",
                input_kind="text",
                placeholder="mira-proxy",
                sensitive=True,
            ),
        ),
        default_config={"permission_mode": "default", "model": "sonnet"},
    ),
    "cursor_agent": BackendDescriptor(
        key="cursor_agent",
        label="Cursor Agent",
        model_options=(
            "auto",
            "composer-2-fast",
            "gpt-5.4-medium",
            "claude-4.5-sonnet",
        ),
        config_fields=(
            BackendConfigField(
                key="mode",
                label="Mode",
                options=(
                    ("Default", "default"),
                    ("Plan", "plan"),
                    ("Ask", "ask"),
                ),
            ),
            BackendConfigField(
                key="sandbox",
                label="Sandbox",
                options=(
                    ("Default", "default"),
                    ("Enabled", "enabled"),
                    ("Disabled", "disabled"),
                ),
            ),
        ),
        default_config={"model": "auto", "mode": "default", "sandbox": "default"},
    ),
    "coco": BackendDescriptor(
        key="coco",
        label="Trae CLI",
        model_options=("GPT-5.2",),
        config_fields=(
            BackendConfigField(
                key="approval_mode",
                label="Permission",
                options=(
                    ("Default", "default"),
                    ("YOLO", "yolo"),
                ),
            ),
        ),
        default_config={"model": "GPT-5.2", "approval_mode": "default"},
    ),
}

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_CURSOR_MODEL_FALLBACK: tuple[tuple[str, str], ...] = (
    ("Auto", "auto"),
    ("Composer 2 Fast", "composer-2-fast"),
    ("GPT-5.4 1M", "gpt-5.4-medium"),
    ("Sonnet 4.5 1M", "claude-4.5-sonnet"),
)
_COCO_MODEL_FALLBACK: tuple[tuple[str, str], ...] = (
    ("GPT-5.2", "GPT-5.2"),
)


def get_backend_descriptor(backend: str) -> BackendDescriptor:
    normalized = (backend or "").strip().lower()
    return _BACKEND_DESCRIPTORS.get(
        normalized,
        BackendDescriptor(key=normalized or "unknown", label=backend or "Unknown"),
    )


def get_backend_model_options(backend: str) -> tuple[tuple[str, str], ...]:
    normalized = (backend or "").strip().lower()
    if normalized == "codex":
        return _discover_codex_model_options(_codex_command())
    if normalized == "cursor_agent":
        return _discover_cursor_model_options(_cursor_command())
    if normalized == "coco":
        return _discover_coco_model_options(_coco_command())
    descriptor = get_backend_descriptor(normalized)
    return tuple((option, option) for option in descriptor.model_options)


def normalize_backend_config(
    backend: str,
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    descriptor = get_backend_descriptor(backend)
    normalized = dict(descriptor.default_config)
    if config:
        normalized.update({key: value for key, value in config.items() if value not in (None, "")})
    if (backend or "").strip().lower() == "cursor_agent":
        normalized = _normalize_cursor_backend_config(normalized)
    return normalized


def backend_option(backend: str, config: dict[str, object], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        value = get_backend_descriptor(backend).default_config.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_cursor_backend_config(config: dict[str, object]) -> dict[str, object]:
    normalized = dict(config)
    model = normalized.get("model")
    if isinstance(model, str) and model.strip() == "gpt-5":
        normalized["model"] = "auto"
    sandbox = normalized.get("sandbox")
    if isinstance(sandbox, str):
        stripped = sandbox.strip()
        if stripped in {"read-only", "workspace-write"}:
            normalized["sandbox"] = "enabled"
        elif stripped == "danger-full-access":
            normalized["sandbox"] = "disabled"
    return normalized


def _cursor_command() -> str:
    return os.getenv("POCO_CURSOR_COMMAND", "cursor-agent")


def _codex_command() -> str:
    return os.getenv("POCO_CODEX_COMMAND", "codex")


def _coco_command() -> str:
    return os.getenv("POCO_COCO_COMMAND", "traecli")


@lru_cache(maxsize=4)
def _discover_codex_model_options(command: str) -> tuple[tuple[str, str], ...]:
    executable = shutil.which(command)
    if not executable:
        return ()
    try:
        result = _request_codex_model_list(command)
    except (OSError, subprocess.SubprocessError, RuntimeError):
        return ()
    return _parse_codex_model_response(result)


@lru_cache(maxsize=4)
def _discover_cursor_model_options(command: str) -> tuple[tuple[str, str], ...]:
    executable = shutil.which(command)
    if not executable:
        return _CURSOR_MODEL_FALLBACK
    try:
        completed = subprocess.run(
            [command, "--list-models"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return _CURSOR_MODEL_FALLBACK
    output = completed.stdout or completed.stderr or ""
    parsed = _parse_cursor_model_output(output)
    return parsed or _CURSOR_MODEL_FALLBACK


@lru_cache(maxsize=4)
def _discover_coco_model_options(command: str) -> tuple[tuple[str, str], ...]:
    executable = shutil.which(command)
    discovered = _request_coco_model_list(command) if executable else ()
    options: list[tuple[str, str]] = list(discovered)
    configured = _read_coco_configured_model()
    if configured:
        configured_option = (configured, configured)
        options = [option for option in options if option != configured_option]
        options.insert(0, configured_option)
    for fallback in _COCO_MODEL_FALLBACK:
        if fallback not in options:
            options.append(fallback)
    return tuple(options)


def _parse_cursor_model_output(output: str) -> tuple[tuple[str, str], ...]:
    options: list[tuple[str, str]] = []
    for raw_line in output.splitlines():
        line = _ANSI_ESCAPE_RE.sub("", raw_line).strip()
        if not line or line == "Available models" or line.startswith("Tip:"):
            continue
        if " - " not in line:
            continue
        model_id, label = line.split(" - ", 1)
        model_id = model_id.strip()
        label = re.sub(r"\s+\(.*\)$", "", label).strip()
        if not model_id:
            continue
        options.append((label or model_id, model_id))
    return tuple(options)


def _request_codex_model_list(command: str) -> dict[str, object]:
    from poco.agent.runner import _CodexAppServerSession

    process = subprocess.Popen(
        [command, "app-server", "--listen", "stdio://"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        session = _CodexAppServerSession(process=process, timeout_seconds=8)
        session.initialize()
        return session.request("model/list", {"includeHidden": False})
    except Exception:
        return {}
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.terminate()


def _request_coco_model_list(command: str) -> tuple[tuple[str, str], ...]:
    from poco.agent.runner import _TraeAcpClient, _cleanup_subprocess

    process = subprocess.Popen(
        [command, "acp", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        session = _TraeAcpClient(process=process)
        session.initialize()
        result = session.open_session(session_id=None, cwd=str(Path.cwd()))
    except Exception:
        return ()
    finally:
        _cleanup_subprocess(process)
    models = result.get("models")
    if not isinstance(models, dict):
        return ()
    available = models.get("availableModels")
    if not isinstance(available, list):
        return ()
    options: list[tuple[str, str]] = []
    for item in available:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("modelId") or "").strip()
        if not model_id:
            continue
        label = str(item.get("name") or model_id).strip()
        options.append((label or model_id, model_id))
    return tuple(options)


def _parse_codex_model_response(result: dict[str, object]) -> tuple[tuple[str, str], ...]:
    data = result.get("data")
    if not isinstance(data, list):
        return ()
    options: list[tuple[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or item.get("model") or "").strip()
        if not model_id:
            continue
        label = str(item.get("displayName") or item.get("model") or model_id).strip()
        options.append((label or model_id, model_id))
    return tuple(options)


def _read_coco_configured_model() -> str | None:
    path = Path.home() / ".trae" / "traecli.yaml"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^\s*name:\s*['\"]?([^'\"]+)['\"]?\s*$", content, flags=re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None
