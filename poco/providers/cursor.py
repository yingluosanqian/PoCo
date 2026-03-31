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
from typing import Dict, List, Optional, Set, Tuple

from .base import ProviderConfig, ProviderNotImplementedError, SessionMeta


LOG = logging.getLogger("poco.providers.cursor")


class CursorSessionLocator:
    provider_name = "cursor"

    def __init__(self, cursor_home: Optional[Path] = None) -> None:
        root = cursor_home or (Path.home() / ".cursor")
        self._projects_dir = root / "projects"
        self._chats_dir = root / "chats"

    def get(self, session_id: str) -> Optional[SessionMeta]:
        session = session_id.strip()
        if not session:
            return None
        try:
            uuid.UUID(session)
        except ValueError:
            return None
        for path in self._projects_dir.glob(f"**/agent-transcripts/{session}/{session}.jsonl"):
            meta = self._read_session_file(path)
            if meta is not None:
                return meta
        return None

    def list_recent(self, limit: int = 10) -> List[SessionMeta]:
        if not self._projects_dir.exists():
            return []
        items: List[Tuple[float, SessionMeta]] = []
        for path in self._projects_dir.glob("**/agent-transcripts/*/*.jsonl"):
            meta = self._read_session_file(path)
            if meta is None:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            items.append((mtime, meta))
        items.sort(key=lambda item: item[0], reverse=True)
        return [meta for _mtime, meta in items[:limit]]

    def delete(self, session_id: str) -> bool:
        meta = self.get(session_id)
        if meta is None:
            return False
        changed = False
        if meta.file_path:
            path = Path(meta.file_path)
            try:
                path.unlink(missing_ok=True)
                changed = True
            except OSError:
                pass
            self._prune_empty_parents(path.parent)
        if self._chats_dir.exists():
            for chat_dir in self._chats_dir.glob(f"**/{session_id}"):
                if not chat_dir.is_dir():
                    continue
                for child in chat_dir.iterdir():
                    try:
                        if child.is_file():
                            child.unlink(missing_ok=True)
                    except OSError:
                        continue
                try:
                    chat_dir.rmdir()
                    changed = True
                except OSError:
                    pass
        return changed

    def _read_session_file(self, path: Path) -> Optional[SessionMeta]:
        session_id = path.stem.strip()
        if not session_id:
            return None
        thread_name = ""
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
                    if str(payload.get("role", "")).strip() != "user":
                        continue
                    message = payload.get("message", {})
                    if not isinstance(message, dict):
                        continue
                    content = message.get("content", [])
                    if not isinstance(content, list):
                        continue
                    text = "".join(
                        str(item.get("text", ""))
                        for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    ).strip()
                    if text:
                        thread_name = self._clean_thread_name(text)
                        break
        except OSError:
            return None
        project_dir = path.parents[2] if len(path.parents) >= 3 else path.parent
        source = project_dir.name
        try:
            updated_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(path.stat().st_mtime))
        except OSError:
            updated_at = ""
        return SessionMeta(
            provider=self.provider_name,
            session_id=session_id,
            cwd="",
            thread_name=thread_name,
            updated_at=updated_at,
            source=source,
            file_path=str(path),
        )

    @staticmethod
    def _clean_thread_name(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("<user_query>") and cleaned.endswith("</user_query>"):
            cleaned = cleaned[len("<user_query>") : -len("</user_query>")].strip()
        return " ".join(cleaned.split())

    def _prune_empty_parents(self, start: Path) -> None:
        current = start
        while current != self._projects_dir and self._projects_dir in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent


class CursorProviderClient:
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
                LOG.exception("Failed to terminate Cursor process")
        self._notify_queue.put({"method": "__closed__"})

    def ensure_thread(self, thread_id: Optional[str]) -> str:
        if thread_id:
            with self._lock:
                self._known_threads.add(thread_id)
            return thread_id
        chat_id = self._create_chat()
        with self._lock:
            self._known_threads.add(chat_id)
        return chat_id

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
            "--print",
            "--output-format",
            "stream-json",
            "--stream-partial-output",
            "--trust",
        ]
        if thread_id:
            cmd.extend(["--resume", thread_id])
        model = self._provider.model.strip()
        if model:
            cmd.extend(["--model", model])
        approval_policy = self._provider.approval_policy.strip().lower()
        if approval_policy in {"force", "yolo"}:
            cmd.append("--force")
        sandbox = self._provider.sandbox.strip().lower()
        if sandbox in {"enabled", "disabled"}:
            cmd.extend(["--sandbox", sandbox])
        extra_args = shlex.split(self._provider.app_server_args)
        cmd.extend(extra_args)
        if local_image_paths:
            image_list = "\n".join(f"- {path}" for path in local_image_paths if path)
            if image_list:
                text = (
                    "Use vision or file tools to inspect the attached image file(s) referenced below. "
                    "Open the image files directly by path when needed.\n"
                    f"{image_list}\n\n"
                    f"User request:\n{text}"
                )
        cmd.append(text)
        env = os.environ.copy()
        env.update(self._provider.env)
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
            name=f"cursor-turn-{turn_id[:8]}",
        ).start()
        threading.Thread(
            target=self._stderr_loop,
            args=(process,),
            daemon=True,
            name=f"cursor-stderr-{turn_id[:8]}",
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
            LOG.exception("Failed to interrupt Cursor turn %s", turn_id)

    def steer_turn(self, thread_id: str, turn_id: str, text: str) -> None:
        raise ProviderNotImplementedError("Cursor provider does not support live steer yet.")

    def _create_chat(self) -> str:
        cmd = [self._provider.bin, "create-chat"]
        env = os.environ.copy()
        env.update(self._provider.env)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self._cwd,
            env=env,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            raise RuntimeError(stderr or stdout or "cursor-agent create-chat failed")
        chat_id = (result.stdout or "").strip().splitlines()[-1].strip()
        if not chat_id:
            raise RuntimeError("cursor-agent create-chat returned an empty chat id")
        return chat_id

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
                LOG.warning("Invalid JSON from Cursor stdout: %s", line)
                continue
            payload_type = str(payload.get("type", "")).strip()
            if payload_type == "system" and str(payload.get("subtype", "")).strip() == "init":
                session_id = str(payload.get("session_id", "")).strip()
                if session_id:
                    with self._lock:
                        self._known_threads.add(session_id)
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
                assistant_text = "".join(text_parts)
                if "timestamp_ms" in payload:
                    accumulated_text += assistant_text
                    self._notify_queue.put(
                        {
                            "method": "item/agentMessage/delta",
                            "params": {
                                "threadId": thread_id,
                                "turnId": turn_id,
                                "delta": assistant_text,
                            },
                        }
                    )
                    continue
                final_text = assistant_text.strip()
                if final_text:
                    accumulated_text = final_text
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
                session_id = str(payload.get("session_id", "")).strip()
                if session_id and not is_error:
                    with self._lock:
                        self._known_threads.add(session_id)
                final_text = str(payload.get("result", "")).strip()
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
                LOG.warning("cursor stderr: %s", line)
