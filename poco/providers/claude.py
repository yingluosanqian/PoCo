import json
import logging
import os
import queue
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set

from .base import ProviderConfig, ProviderNotImplementedError, SessionMeta


LOG = logging.getLogger("poco.providers.claude")


class ClaudeSessionLocator:
    provider_name = "claude"

    def __init__(self, claude_home: Optional[Path] = None) -> None:
        root = claude_home or (Path.home() / ".claude")
        self._projects_dir = root / "projects"

    def get(self, session_id: str) -> Optional[SessionMeta]:
        session_id = session_id.strip()
        if not session_id or not self._projects_dir.exists():
            return None
        for path in self._projects_dir.glob(f"**/{session_id}.jsonl"):
            meta = self._read_session_file(path)
            if meta is not None and meta.session_id == session_id:
                return meta
        return None

    def list_recent(self, limit: int = 10) -> List[SessionMeta]:
        if not self._projects_dir.exists():
            return []
        results: List[SessionMeta] = []
        for path in self._projects_dir.glob("**/*.jsonl"):
            if path.parent.name == "subagents":
                continue
            if path.name == "history.jsonl":
                continue
            meta = self._read_session_file(path)
            if meta is not None:
                results.append(meta)
        results.sort(key=lambda item: item.updated_at, reverse=True)
        return results[:limit]

    def delete(self, session_id: str) -> bool:
        meta = self.get(session_id)
        if meta is None or not meta.file_path:
            return False
        path = Path(meta.file_path)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
        self._prune_empty_parents(path.parent)
        return True

    def _read_session_file(self, path: Path) -> Optional[SessionMeta]:
        session_id = path.stem.strip()
        if not session_id:
            return None
        cwd = ""
        thread_name = ""
        updated_at = ""
        source = ""
        originator = ""
        try:
            with path.open(encoding="utf-8") as handle:
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
                    updated_at = str(payload.get("timestamp", "")).strip() or updated_at
                    entry_cwd = str(payload.get("cwd", "")).strip()
                    if entry_cwd:
                        cwd = entry_cwd
                    entry_source = str(payload.get("entrypoint", "")).strip()
                    if entry_source:
                        source = entry_source
                    entry_originator = str(payload.get("userType", "")).strip()
                    if entry_originator:
                        originator = entry_originator
                    payload_type = str(payload.get("type", "")).strip()
                    if payload_type == "last-prompt":
                        prompt = str(payload.get("lastPrompt", "")).strip()
                        if prompt:
                            thread_name = prompt
                    elif payload_type == "user":
                        message = payload.get("message", {})
                        if isinstance(message, dict):
                            content = message.get("content", "")
                            if isinstance(content, str) and content.strip() and not thread_name:
                                thread_name = content.strip()
        except OSError:
            return None
        if not updated_at:
            try:
                updated_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(path.stat().st_mtime))
            except OSError:
                updated_at = ""
        return SessionMeta(
            provider=self.provider_name,
            session_id=session_id,
            cwd=cwd,
            thread_name=thread_name,
            updated_at=updated_at,
            source=source,
            originator=originator,
            file_path=str(path),
        )

    def _prune_empty_parents(self, start: Path) -> None:
        current = start
        while current != self._projects_dir and self._projects_dir in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent


class ClaudeProviderClient:
    def __init__(self, provider_config: ProviderConfig, cwd: str) -> None:
        self._provider = provider_config
        self._cwd = cwd
        self._notify_queue: "queue.Queue[dict]" = queue.Queue()
        self._processes: Dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()
        self._interrupted_turns: Set[str] = set()
        self._known_threads: Set[str] = set()

    def start(self) -> None:
        return None

    def notifications(self) -> "queue.Queue[dict]":
        return self._notify_queue

    def close(self) -> None:
        with self._lock:
            items = list(self._processes.items())
            self._processes.clear()
            self._interrupted_turns.update(turn_id for turn_id, _proc in items)
        for _turn_id, process in items:
            try:
                process.terminate()
            except Exception:
                LOG.exception("Failed to terminate Claude process")
        self._notify_queue.put({"method": "__closed__"})

    def ensure_thread(self, thread_id: Optional[str]) -> str:
        if thread_id:
            return thread_id
        return str(uuid.uuid4())

    def start_turn(
        self,
        thread_id: str,
        text: str,
        local_image_paths: Optional[List[str]] = None,
    ) -> str:
        turn_id = str(uuid.uuid4())
        cmd = [
            self._provider.bin,
            "-p",
            "--verbose",
            "--output-format",
            "stream-json",
            "--include-partial-messages",
        ]
        use_resume = self._has_thread(thread_id)
        if use_resume:
            cmd.extend(["--resume", thread_id])
        else:
            cmd.extend(["--session-id", thread_id])
        if self._provider.model:
            cmd.extend(["--model", self._provider.model])
        approval_policy = self._provider.approval_policy.strip()
        if approval_policy in {"bypassPermissions", "dangerously-skip-permissions"}:
            cmd.append("--dangerously-skip-permissions")
        elif approval_policy:
            cmd.extend(["--permission-mode", self._provider.approval_policy])
        image_paths = [path for path in (local_image_paths or []) if path]
        for parent in sorted({str(Path(path).expanduser().resolve().parent) for path in image_paths}):
            cmd.extend(["--add-dir", parent])
        extra_args = shlex.split(self._provider.app_server_args)
        cmd.extend(extra_args)
        if image_paths:
            image_list = "\n".join(f"- {path}" for path in image_paths)
            text = (
                "Use vision to inspect the attached image file(s) referenced below. "
                "Open the image files directly by path when needed.\n"
                f"{image_list}\n\n"
                f"User request:\n{text}"
            )
        cmd.append(text)
        env = os.environ.copy()
        env.update(self._provider.env)
        if str(self._provider.sandbox).strip() in {"1", "true", "True", "sandbox", "is_sandbox"}:
            env["IS_SANDBOX"] = "1"
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=self._cwd,
            env=env,
        )
        with self._lock:
            self._processes[turn_id] = process
        threading.Thread(
            target=self._stdout_loop,
            args=(thread_id, turn_id, process),
            daemon=True,
            name=f"claude-turn-{turn_id[:8]}",
        ).start()
        threading.Thread(
            target=self._stderr_loop,
            args=(process,),
            daemon=True,
            name=f"claude-stderr-{turn_id[:8]}",
        ).start()
        return turn_id

    def interrupt_turn(self, thread_id: str, turn_id: str) -> None:
        with self._lock:
            process = self._processes.get(turn_id)
            if process is None:
                return
            self._interrupted_turns.add(turn_id)
        try:
            process.terminate()
        except Exception:
            LOG.exception("Failed to interrupt Claude turn %s", turn_id)

    def steer_turn(self, thread_id: str, turn_id: str, text: str) -> None:
        raise ProviderNotImplementedError(
            "Claude provider does not support live steer yet."
        )

    def _stdout_loop(self, thread_id: str, turn_id: str, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        accumulated_text = ""
        emitted_completed = False
        saw_result = False
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                LOG.warning("Invalid JSON from Claude stdout: %s", line)
                continue
            payload_type = str(payload.get("type", "")).strip()
            if payload_type == "stream_event":
                event = payload.get("event", {})
                if not isinstance(event, dict):
                    continue
                if event.get("type") != "content_block_delta":
                    continue
                delta = event.get("delta", {})
                if not isinstance(delta, dict):
                    continue
                if delta.get("type") != "text_delta":
                    continue
                text_delta = str(delta.get("text", ""))
                if not text_delta:
                    continue
                accumulated_text += text_delta
                self._notify_queue.put(
                    {
                        "method": "item/agentMessage/delta",
                        "params": {
                            "threadId": thread_id,
                            "turnId": turn_id,
                            "delta": text_delta,
                        },
                    }
                )
                continue
            if payload_type == "assistant":
                message = payload.get("message", {})
                if not isinstance(message, dict):
                    continue
                content = message.get("content", [])
                if not isinstance(content, list):
                    continue
                text_parts = [
                    str(item.get("text", ""))
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text" and str(item.get("text", ""))
                ]
                if not text_parts:
                    continue
                final_text = "".join(text_parts).strip()
                if final_text and final_text != accumulated_text:
                    accumulated_text = final_text
                if final_text:
                    self._notify_queue.put(
                        {
                            "method": "item/completed",
                            "params": {
                                "threadId": thread_id,
                                "turnId": turn_id,
                                "item": {
                                    "type": "agentMessage",
                                    "text": final_text,
                                },
                            },
                        }
                    )
                    emitted_completed = True
                continue
            if payload_type == "result":
                saw_result = True
                is_error = bool(payload.get("is_error", False))
                final_text = str(payload.get("result", "")).strip()
                if not is_error:
                    with self._lock:
                        self._known_threads.add(thread_id)
                if final_text and not emitted_completed:
                    self._notify_queue.put(
                        {
                            "method": "item/completed",
                            "params": {
                                "threadId": thread_id,
                                "turnId": turn_id,
                                "item": {
                                    "type": "agentMessage",
                                    "text": final_text,
                                },
                            },
                        }
                    )
                status = "completed" if not is_error else "failed"
                self._notify_queue.put(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": thread_id,
                            "turn": {
                                "id": turn_id,
                                "status": status,
                            },
                        },
                    }
                )
                break
        exit_code = process.wait()
        with self._lock:
            self._processes.pop(turn_id, None)
            interrupted = turn_id in self._interrupted_turns
            if interrupted:
                self._interrupted_turns.remove(turn_id)
        if not saw_result:
            status = "interrupted" if interrupted else ("completed" if exit_code == 0 else "failed")
            self._notify_queue.put(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": thread_id,
                        "turn": {
                            "id": turn_id,
                            "status": status,
                        },
                    },
                }
            )

    def _stderr_loop(self, process: subprocess.Popen[str]) -> None:
        assert process.stderr is not None
        for raw_line in process.stderr:
            line = raw_line.rstrip("\n")
            if line:
                LOG.warning("claude stderr: %s", line)

    def _has_thread(self, thread_id: str) -> bool:
        with self._lock:
            if thread_id in self._known_threads:
                return True
        projects_dir = Path.home() / ".claude" / "projects"
        if not projects_dir.exists():
            return False
        for path in projects_dir.glob(f"**/{thread_id}.jsonl"):
            if path.parent.name != "subagents":
                return True
        return False
