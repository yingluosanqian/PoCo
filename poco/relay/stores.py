"""Persistent state stores used by the relay runtime."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Dict, Optional


LOG = logging.getLogger("poco.relay")


class ThreadStore:
    """Persists worker-to-thread bindings."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data = {str(k): str(v) for k, v in raw.items()}
        except Exception:
            LOG.warning("Failed to load thread state from %s", self._path)

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, chat_id: str) -> Optional[str]:
        with self._lock:
            return self._data.get(chat_id)

    def set(self, chat_id: str, thread_id: str) -> None:
        with self._lock:
            self._data[chat_id] = thread_id
            self._save()

    def clear(self, chat_id: str) -> None:
        with self._lock:
            if chat_id in self._data:
                del self._data[chat_id]
                self._save()


class WorkerStore:
    """Persists per-group worker configuration."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, object]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cleaned: Dict[str, Dict[str, object]] = {}
                for worker_id, payload in raw.items():
                    if not isinstance(payload, dict):
                        continue
                    alias = str(payload.get("alias", "")).strip()
                    provider = str(payload.get("provider", "")).strip().lower() or "codex"
                    backend = str(payload.get("backend", "")).strip().lower()
                    if not backend:
                        backend = "openai" if provider == "codex" else ""
                    mode = str(payload.get("mode", "auto")).strip() or "auto"
                    enabled = bool(payload.get("enabled", False))
                    cwd = str(payload.get("cwd", "")).strip()
                    model = str(payload.get("model", "")).strip()
                    cleaned[str(worker_id)] = {
                        "alias": alias,
                        "provider": provider,
                        "backend": backend,
                        "mode": mode,
                        "model": model,
                        "enabled": enabled,
                        "cwd": cwd,
                    }
                self._data = cleaned
        except Exception:
            LOG.warning("Failed to load worker state from %s", self._path)

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def alias_for(self, worker_id: str) -> str:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return str(payload.get("alias", "")).strip()

    def provider_for(self, worker_id: str) -> str:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return str(payload.get("provider", "")).strip().lower()

    def backend_for(self, worker_id: str) -> str:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return str(payload.get("backend", "")).strip().lower()

    def set_provider(self, worker_id: str, provider: str) -> None:
        provider_value = provider.strip().lower()
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["provider"] = provider_value
            payload["backend"] = ""
            payload["model"] = ""
            self._save()

    def set_backend(self, worker_id: str, backend: str) -> None:
        backend_value = backend.strip().lower()
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["backend"] = backend_value
            payload["model"] = ""
            self._save()

    def set_alias(self, worker_id: str, alias: str) -> None:
        alias = alias.strip()
        with self._lock:
            for existing_worker_id, payload in list(self._data.items()):
                if existing_worker_id != worker_id and payload.get("alias", "") == alias:
                    raise ValueError(f"别名 {alias} 已被 worker {existing_worker_id} 使用。")
            record = self._ensure_record_locked(worker_id)
            record["alias"] = alias
            self._save()

    def alias_in_use(self, alias: str, *, except_worker_id: str = "") -> bool:
        alias_value = alias.strip()
        if not alias_value:
            return False
        with self._lock:
            for worker_id, payload in self._data.items():
                if except_worker_id and worker_id == except_worker_id:
                    continue
                if str(payload.get("alias", "")).strip() == alias_value:
                    return True
        return False

    def clear_alias(self, worker_id: str) -> None:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["alias"] = ""
            self._save()

    def mode_for(self, worker_id: str) -> str:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return str(payload.get("mode", "auto")).strip() or "auto"

    def set_mode(self, worker_id: str, mode: str) -> None:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["mode"] = mode
            self._save()

    def enabled_for(self, worker_id: str) -> bool:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return bool(payload.get("enabled", False))

    def set_enabled(self, worker_id: str, enabled: bool) -> None:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["enabled"] = enabled
            self._save()

    def ensure_worker(self, worker_id: str) -> None:
        with self._lock:
            self._ensure_record_locked(worker_id)
            self._save()

    def cwd_for(self, worker_id: str) -> str:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return str(payload.get("cwd", "")).strip()

    def set_cwd(self, worker_id: str, cwd: str) -> None:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["cwd"] = cwd.strip()
            self._save()

    def model_for(self, worker_id: str) -> str:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            return str(payload.get("model", "")).strip()

    def set_model(self, worker_id: str, model: str) -> None:
        with self._lock:
            payload = self._ensure_record_locked(worker_id)
            payload["model"] = model.strip()
            self._save()

    def resolve(self, identifier: str) -> Optional[str]:
        key = identifier.strip()
        if not key:
            return None
        with self._lock:
            if key in self._data:
                return key
            for worker_id, payload in self._data.items():
                if payload.get("alias", "") == key:
                    return worker_id
        return key if key.startswith("oc_") else None

    def items(self) -> list[tuple[str, str]]:
        with self._lock:
            return sorted((worker_id, payload.get("alias", "")) for worker_id, payload in self._data.items())

    def remove(self, worker_id: str) -> None:
        with self._lock:
            if worker_id in self._data:
                del self._data[worker_id]
                self._save()

    def _ensure_record_locked(self, worker_id: str) -> Dict[str, object]:
        payload = self._data.get(worker_id)
        if payload is None:
            payload = {
                "alias": "",
                "provider": "codex",
                "backend": "openai",
                "mode": "auto",
                "model": "",
                "enabled": False,
                "cwd": "",
            }
            self._data[worker_id] = payload
        return payload
