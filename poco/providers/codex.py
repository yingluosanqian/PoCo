import json
import logging
import queue
import shlex
import subprocess
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set

from .base import ProviderConfig, ProviderClient, SessionLocator, SessionMeta


LOG = logging.getLogger("poco.providers.codex")


class CodexSessionLocator:
    provider_name = "codex"

    def __init__(self, codex_home: Optional[Path] = None) -> None:
        root = codex_home or (Path.home() / ".codex")
        self._sessions_dir = root / "sessions"
        self._session_index_path = root / "session_index.jsonl"

    def get(self, session_id: str) -> Optional[SessionMeta]:
        session_id = session_id.strip()
        if not session_id or not self._sessions_dir.exists():
            return None
        index_items = self._session_index_items()
        for path in self._sessions_dir.rglob("*.jsonl"):
            payload = self._read_session_meta_payload(path)
            if payload is None:
                continue
            if str(payload.get("id", "")).strip() != session_id:
                continue
            index_item = index_items.get(session_id, {})
            return SessionMeta(
                provider=self.provider_name,
                session_id=session_id,
                cwd=str(payload.get("cwd", "")).strip(),
                thread_name=str(index_item.get("thread_name") or payload.get("thread_name", "")).strip(),
                updated_at=str(index_item.get("updated_at") or payload.get("timestamp", "")).strip(),
                source=str(payload.get("source", "")).strip(),
                originator=str(payload.get("originator", "")).strip(),
                file_path=str(path),
            )
        return None

    def list_recent(self, limit: int = 10) -> List[SessionMeta]:
        index_items = self._session_index_items()
        merged: Dict[str, SessionMeta] = {}

        for path in self._sessions_dir.rglob("*.jsonl") if self._sessions_dir.exists() else []:
            payload = self._read_session_meta_payload(path)
            if payload is None:
                continue
            session_id = str(payload.get("id", "")).strip()
            if not session_id:
                continue
            index_item = index_items.get(session_id, {})
            merged[session_id] = SessionMeta(
                provider=self.provider_name,
                session_id=session_id,
                cwd=str(payload.get("cwd", "")).strip(),
                thread_name=str(index_item.get("thread_name") or payload.get("thread_name", "")).strip(),
                updated_at=str(index_item.get("updated_at") or payload.get("timestamp", "")).strip(),
                source=str(payload.get("source", "")).strip(),
                originator=str(payload.get("originator", "")).strip(),
                file_path=str(path),
            )

        for session_id, item in index_items.items():
            if session_id in merged:
                continue
            merged[session_id] = SessionMeta(
                provider=self.provider_name,
                session_id=session_id,
                cwd="",
                thread_name=str(item.get("thread_name", "")).strip(),
                updated_at=str(item.get("updated_at", "")).strip(),
            )

        results = list(merged.values())
        results.sort(key=lambda item: item.updated_at, reverse=True)
        return results[:limit]

    def delete(self, session_id: str) -> bool:
        session_id = session_id.strip()
        if not session_id:
            return False
        changed = False
        meta = self.get(session_id)
        if meta is not None and meta.file_path:
            path = Path(meta.file_path)
            try:
                path.unlink(missing_ok=True)
                changed = True
            except OSError:
                pass
            self._prune_empty_parents(path.parent)
        if self._session_index_path.exists():
            try:
                lines = self._session_index_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            kept: List[str] = []
            removed = False
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    kept.append(line)
                    continue
                if isinstance(payload, dict) and str(payload.get("id", "")).strip() == session_id:
                    removed = True
                    continue
                kept.append(line)
            if removed:
                try:
                    content = "\n".join(kept)
                    if content:
                        content += "\n"
                    self._session_index_path.write_text(content, encoding="utf-8")
                    changed = True
                except OSError:
                    pass
        return changed

    def _session_index_items(self) -> Dict[str, Dict[str, str]]:
        if not self._session_index_path.exists():
            return {}
        items: Dict[str, Dict[str, str]] = {}
        try:
            with self._session_index_path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    session_id = str(payload.get("id", "")).strip()
                    if not session_id:
                        continue
                    items[session_id] = {
                        "id": session_id,
                        "thread_name": str(payload.get("thread_name", "")).strip(),
                        "updated_at": str(payload.get("updated_at", "")).strip(),
                    }
        except OSError:
            return {}
        return items

    @staticmethod
    def _read_session_meta_payload(path: Path) -> Optional[dict]:
        try:
            with path.open(encoding="utf-8") as handle:
                first_line = handle.readline()
        except OSError:
            return None
        if not first_line:
            return None
        try:
            message = json.loads(first_line)
        except json.JSONDecodeError:
            return None
        if message.get("type") != "session_meta":
            return None
        payload = message.get("payload", {})
        return payload if isinstance(payload, dict) else None

    def _prune_empty_parents(self, start: Path) -> None:
        current = start
        while current != self._sessions_dir and self._sessions_dir in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent


class CodexProviderClient:
    def __init__(self, provider_config: ProviderConfig, cwd: str) -> None:
        self._provider = provider_config
        self._cwd = cwd
        self._process: Optional[subprocess.Popen[str]] = None
        self._request_id = 0
        self._responses: Dict[int, "queue.Queue[dict]"] = {}
        self._responses_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._notify_queue: "queue.Queue[dict]" = queue.Queue()
        self._loaded_threads: Set[str] = set()

    def start(self) -> None:
        cmd = [self._provider.bin, "app-server"]
        extra_args = shlex.split(self._provider.app_server_args)
        cmd.extend(extra_args)
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        assert self._process.stderr is not None
        threading.Thread(target=self._stdout_loop, daemon=True).start()
        threading.Thread(target=self._stderr_loop, daemon=True).start()
        self._request(
            "initialize",
            {
                "clientInfo": {"name": "poco-provider-bridge", "version": "0.2.1"},
                "capabilities": {"experimentalApi": True},
            },
        )

    def notifications(self) -> "queue.Queue[dict]":
        return self._notify_queue

    def close(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
        except Exception:
            LOG.exception("Failed to terminate app-server")
        try:
            self._notify_queue.put({"method": "__closed__"})
        except Exception:
            LOG.exception("Failed to notify app-server close")
        self._process = None

    def _stdout_loop(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        for raw_line in self._process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                LOG.warning("Invalid JSON from app-server stdout: %s", line)
                continue
            if "id" in message and ("result" in message or "error" in message):
                self._handle_response(message)
            elif "method" in message:
                self._notify_queue.put(message)
            else:
                continue

    def _stderr_loop(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None
        for raw_line in self._process.stderr:
            line = raw_line.rstrip("\n")
            if line:
                LOG.warning("app-server stderr: %s", line)

    def _handle_response(self, message: dict) -> None:
        response_id = message.get("id")
        if not isinstance(response_id, int):
            return
        with self._responses_lock:
            waiter = self._responses.get(response_id)
        if waiter is not None:
            waiter.put(message)

    def _request(self, method: str, params: dict, timeout: float = 30.0) -> dict:
        if self._process is None or self._process.poll() is not None:
            raise RuntimeError("app-server is not running")
        with self._responses_lock:
            self._request_id += 1
            request_id = self._request_id
            waiter: "queue.Queue[dict]" = queue.Queue(maxsize=1)
            self._responses[request_id] = waiter
        message = {"id": request_id, "method": method, "params": params}
        with self._write_lock:
            assert self._process.stdin is not None
            self._process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
        try:
            response = waiter.get(timeout=timeout)
        except queue.Empty as exc:
            raise RuntimeError(f"app-server request timed out: {method}") from exc
        finally:
            with self._responses_lock:
                self._responses.pop(request_id, None)
        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"app-server error on {method}: {error}")
        return response["result"]

    def ensure_thread(self, thread_id: Optional[str]) -> str:
        if thread_id:
            if thread_id not in self._loaded_threads:
                self._request(
                    "thread/resume",
                    {
                        "threadId": thread_id,
                        "cwd": self._cwd,
                        "approvalPolicy": self._provider.approval_policy,
                        "sandbox": self._provider.sandbox,
                        "model": self._provider.model or None,
                        "reasoningEffort": self._provider.reasoning_effort or None,
                    },
                )
                self._loaded_threads.add(thread_id)
            return thread_id
        result = self._request(
            "thread/start",
            {
                "cwd": self._cwd,
                "approvalPolicy": self._provider.approval_policy,
                "sandbox": self._provider.sandbox,
                "model": self._provider.model or None,
                "reasoningEffort": self._provider.reasoning_effort or None,
            },
        )
        new_thread_id = result["thread"]["id"]
        self._loaded_threads.add(new_thread_id)
        return new_thread_id

    def start_turn(
        self,
        thread_id: str,
        text: str,
        local_image_paths: Optional[List[str]] = None,
    ) -> str:
        input_items = []
        for path in local_image_paths or []:
            input_items.append({"type": "localImage", "path": path})
        input_items.append({"type": "text", "text": text})
        result = self._request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": input_items,
            },
            timeout=60.0,
        )
        return result["turn"]["id"]

    def interrupt_turn(self, thread_id: str, turn_id: str) -> None:
        self._request(
            "turn/interrupt",
            {"threadId": thread_id, "turnId": turn_id},
            timeout=10.0,
        )

    def steer_turn(self, thread_id: str, turn_id: str, text: str) -> None:
        self._request(
            "turn/steer",
            {
                "threadId": thread_id,
                "expectedTurnId": turn_id,
                "input": [{"type": "text", "text": text}],
            },
            timeout=30.0,
        )
