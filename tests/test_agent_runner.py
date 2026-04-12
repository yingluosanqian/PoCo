from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from poco.agent.runner import (
    ClaudeCodeRunner,
    CocoRunner,
    CodexAppServerRunner,
    CodexCliRunner,
    CursorAgentRunner,
    _cleanup_subprocess,
)
from poco.task.models import Task, TaskStatus


class CodexCliRunnerTest(unittest.TestCase):
    def _fake_popen_factory(
        self,
        *,
        output_text: str,
        stream_lines: list[str] | None = None,
        returncode: int = 0,
        captured: dict[str, object] | None = None,
    ):
        class FakeStdout:
            def __init__(self, lines: list[str]) -> None:
                self._lines = iter(lines)

            def __iter__(self):
                return self

            def __next__(self) -> str:
                return next(self._lines)

            def close(self) -> None:
                return None

        class FakePopen:
            def __init__(self, command, **kwargs):  # type: ignore[no-untyped-def]
                if captured is not None:
                    captured["command"] = command
                    captured["cwd"] = kwargs.get("cwd")
                output_index = command.index("-o") + 1
                Path(command[output_index]).write_text(output_text, encoding="utf-8")
                self.stdout = FakeStdout(stream_lines or [])
                self._returncode = returncode

            def wait(self, timeout=None):  # type: ignore[no-untyped-def]
                return self._returncode

            def kill(self) -> None:
                return None

        return FakePopen

    def test_is_ready_fails_when_binary_is_missing(self) -> None:
        runner = CodexCliRunner(command="missing-codex", workdir="/tmp")
        with patch("poco.agent.runner.shutil.which", return_value=None):
            ready, detail = runner.is_ready()
        self.assertFalse(ready)
        self.assertIn("Codex CLI not found", detail)

    def test_confirm_prefix_requires_approval_before_running_codex(self) -> None:
        runner = CodexCliRunner(command="codex", workdir="/tmp")
        task = Task(
            id="task1",
            requester_id="ou_demo",
            prompt="confirm: refactor the API layer",
            source="feishu",
            status=TaskStatus.RUNNING,
            agent_backend="codex",
        )
        updates = list(runner.start(task))
        self.assertEqual(updates[-1].kind, "confirmation_required")

    def test_codex_success_reads_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexCliRunner(command="codex", workdir=tmpdir)
            task = Task(
                id="task2",
                requester_id="ou_demo",
                prompt="summarize this project",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
            )

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch(
                    "poco.agent.runner.subprocess.Popen",
                    self._fake_popen_factory(
                        output_text="codex final answer",
                        stream_lines=[
                            '{"type":"thread.started","thread_id":"thread_123"}\n',
                            '{"type":"item.completed","item":{"type":"agent_message","text":"step 1"}}\n',
                        ],
                    ),
                ):
                    updates = list(runner.start(task))

            self.assertEqual(updates[1].kind, "progress")
            self.assertEqual(updates[1].backend_session_id, "thread_123")
            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].result_summary, "codex final answer")
            self.assertEqual(updates[-1].backend_session_id, "thread_123")

    def test_codex_prefers_task_effective_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as default_tmpdir, tempfile.TemporaryDirectory() as task_tmpdir:
            runner = CodexCliRunner(command="codex", workdir=default_tmpdir)
            task = Task(
                id="task_workdir",
                requester_id="ou_demo",
                prompt="summarize this project",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
                effective_workdir=task_tmpdir,
            )
            captured: dict[str, object] = {}

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch(
                    "poco.agent.runner.subprocess.Popen",
                    self._fake_popen_factory(
                        output_text="codex final answer",
                        captured=captured,
                    ),
                ):
                    updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(captured["cwd"], task_tmpdir)
            self.assertEqual(captured["command"][captured["command"].index("-C") + 1], task_tmpdir)

    def test_codex_resume_uses_existing_backend_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexCliRunner(command="codex", workdir=tmpdir)
            task = Task(
                id="task_resume",
                requester_id="ou_demo",
                prompt="continue from before",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
                backend_session_id="thread_123",
            )
            captured: dict[str, object] = {}

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch(
                    "poco.agent.runner.subprocess.Popen",
                    self._fake_popen_factory(
                        output_text="continued answer",
                        stream_lines=['{"type":"thread.started","thread_id":"thread_123"}\n'],
                        captured=captured,
                    ),
                ):
                    updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "completed")
            self.assertIn("resume", captured["command"])
            self.assertIn("thread_123", captured["command"])
            self.assertNotIn("-C", captured["command"])

    def test_codex_failure_maps_to_failed_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexCliRunner(command="codex", workdir=tmpdir)
            task = Task(
                id="task3",
                requester_id="ou_demo",
                prompt="summarize this project",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
            )

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch(
                    "poco.agent.runner.subprocess.Popen",
                    self._fake_popen_factory(
                        output_text="",
                        stream_lines=["codex failed\n"],
                        returncode=1,
                    ),
                ):
                    updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "failed")
            self.assertIn("codex failed", updates[-1].message)

    def test_cancel_kills_active_process(self) -> None:
        class FakePopen:
            def __init__(self) -> None:
                self.killed = False

            def kill(self) -> None:
                self.killed = True

        runner = CodexCliRunner(command="codex", workdir="/tmp")
        process = FakePopen()
        runner._active_processes["task_cancel"] = process  # type: ignore[attr-defined]

        cancelled = runner.cancel("task_cancel")

        self.assertTrue(cancelled)
        self.assertTrue(process.killed)


class CodexAppServerRunnerTest(unittest.TestCase):
    def test_app_server_runner_streams_deltas_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexAppServerRunner(command="codex", workdir=tmpdir)
            task = Task(
                id="task_stream",
                requester_id="ou_demo",
                prompt="stream output",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
            )

            class FakePopen:
                def __init__(self) -> None:
                    self.killed = False

                def poll(self):  # type: ignore[no-untyped-def]
                    return 0 if self.killed else None

                def kill(self) -> None:
                    self.killed = True

            fake_session = MagicMock()
            fake_session.request.side_effect = [
                {"thread": {"id": "thread_123"}},
                {"turn": {"id": "turn_123"}},
            ]
            fake_session.read_next_message.side_effect = [
                {
                    "method": "item/agentMessage/delta",
                    "params": {
                        "threadId": "thread_123",
                        "turnId": "turn_123",
                        "itemId": "msg_1",
                        "delta": "line1",
                    },
                },
                {
                    "method": "item/agentMessage/delta",
                    "params": {
                        "threadId": "thread_123",
                        "turnId": "turn_123",
                        "itemId": "msg_1",
                        "delta": "\nline2",
                    },
                },
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread_123",
                        "turnId": "turn_123",
                        "item": {"type": "agentMessage", "text": "line1\nline2"},
                    },
                },
                {
                    "method": "thread/status/changed",
                    "params": {
                        "threadId": "thread_123",
                        "status": {"type": "idle"},
                    },
                },
            ]

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch("poco.agent.runner.subprocess.Popen", return_value=FakePopen()):
                    with patch("poco.agent.runner._CodexAppServerSession", return_value=fake_session):
                        updates = list(runner.start(task))

            self.assertEqual(updates[1].kind, "progress")
            self.assertEqual(updates[1].backend_session_id, "thread_123")
            self.assertEqual(updates[2].output_chunk, "line1")
            self.assertEqual(updates[3].output_chunk, "\nline2")
            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].raw_result, "line1\nline2")

    def test_app_server_runner_resumes_existing_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexAppServerRunner(command="codex", workdir=tmpdir)
            task = Task(
                id="task_resume",
                requester_id="ou_demo",
                prompt="continue from before",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
                backend_session_id="thread_existing",
            )

            class FakePopen:
                def poll(self):  # type: ignore[no-untyped-def]
                    return None

                def kill(self) -> None:
                    return None

            fake_session = MagicMock()
            fake_session.request.side_effect = [
                {"thread": {"id": "thread_existing"}},
                {"turn": {"id": "turn_123"}},
            ]
            fake_session.read_next_message.side_effect = [
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread_existing",
                        "turnId": "turn_123",
                        "item": {"type": "agentMessage", "text": "continued answer"},
                    },
                },
                {
                    "method": "thread/status/changed",
                    "params": {
                        "threadId": "thread_existing",
                        "status": {"type": "idle"},
                    },
                },
            ]

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch("poco.agent.runner.subprocess.Popen", return_value=FakePopen()):
                    with patch("poco.agent.runner._CodexAppServerSession", return_value=fake_session):
                        updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].backend_session_id, "thread_existing")
            first_call = fake_session.request.call_args_list[0]
            self.assertEqual(first_call.args[0], "thread/resume")
            self.assertEqual(first_call.args[1]["threadId"], "thread_existing")


class ClaudeCodeRunnerTest(unittest.TestCase):
    def test_claude_runner_streams_deltas_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ClaudeCodeRunner(command="claude", workdir=tmpdir, model="sonnet")
            task = Task(
                id="claude_task_stream",
                requester_id="ou_demo",
                prompt="stream output",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="claude_code",
            )

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False
                    self._lines = iter(
                        [
                            '{"type":"system","subtype":"init","session_id":"session_123"}\n',
                            '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}}\n',
                            '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}}\n',
                            '{"type":"result","subtype":"success","result":"Hello world","session_id":"session_123"}\n',
                        ]
                    )

                def readline(self) -> str:
                    line = next(self._lines, "")
                    if not line:
                        self.exhausted = True
                    return line

            class FakeStderr:
                exhausted = True

                def readline(self) -> str:
                    return ""

            class FakePopen:
                def __init__(self) -> None:
                    self.stdout = FakeStdout()
                    self.stderr = FakeStderr()
                    self.returncode = 0
                    self.killed = False

                def poll(self):  # type: ignore[no-untyped-def]
                    return 0 if self.killed or self.stdout.exhausted else None

                def kill(self) -> None:
                    self.killed = True
                    self.returncode = -9

            fake_process = FakePopen()
            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/yihanc/.local/bin/claude"),
                patch("poco.agent.runner.subprocess.Popen", return_value=fake_process),
                patch(
                    "poco.agent.runner.select.select",
                    side_effect=lambda readers, *_args: ([reader for reader in readers if not getattr(reader, "exhausted", True)], [], []),
                ),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[1].backend_session_id, "session_123")
            self.assertEqual(updates[2].output_chunk, "Hello")
            self.assertEqual(updates[3].output_chunk, " world")
            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].raw_result, "Hello world")

    def test_claude_runner_resumes_existing_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ClaudeCodeRunner(command="claude", workdir=tmpdir, model="sonnet")
            task = Task(
                id="claude_task_resume",
                requester_id="ou_demo",
                prompt="continue",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="claude_code",
                backend_session_id="session_existing",
                effective_backend_config={"permission_mode": "default"},
            )
            captured: dict[str, object] = {}

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False
                    self._lines = iter(
                        [
                            '{"type":"result","subtype":"success","result":"continued","session_id":"session_existing"}\n',
                        ]
                    )

                def readline(self) -> str:
                    line = next(self._lines, "")
                    if not line:
                        self.exhausted = True
                    return line

            class FakeStderr:
                exhausted = True

                def readline(self) -> str:
                    return ""

            class FakePopen:
                def __init__(self, command, **kwargs):  # type: ignore[no-untyped-def]
                    captured["command"] = command
                    captured["cwd"] = kwargs.get("cwd")
                    self.stdout = FakeStdout()
                    self.stderr = FakeStderr()
                    self.returncode = 0

                def poll(self):  # type: ignore[no-untyped-def]
                    return 0

                def kill(self) -> None:
                    return None

            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/yihanc/.local/bin/claude"),
                patch("poco.agent.runner.subprocess.Popen", FakePopen),
                patch(
                    "poco.agent.runner.select.select",
                    side_effect=lambda readers, *_args: ([reader for reader in readers if not getattr(reader, "exhausted", True)], [], []),
                ),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[-1].backend_session_id, "session_existing")
            self.assertIn("--resume", captured["command"])
            self.assertIn("session_existing", captured["command"])

    def test_claude_runner_sets_is_sandbox_for_bypass_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ClaudeCodeRunner(command="claude", workdir=tmpdir, model="sonnet")
            task = Task(
                id="claude_task_bypass",
                requester_id="ou_demo",
                prompt="do it",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="claude_code",
                effective_backend_config={"permission_mode": "bypassPermissions"},
            )
            captured: dict[str, object] = {}

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False

                def readline(self) -> str:
                    if self.exhausted:
                        return ""
                    self.exhausted = True
                    return '{"type":"result","subtype":"success","result":"done","session_id":"session_bypass"}\n'

            class FakeStderr:
                exhausted = True

                def readline(self) -> str:
                    return ""

            class FakePopen:
                def __init__(self, command, **kwargs):  # type: ignore[no-untyped-def]
                    captured["command"] = command
                    captured["env"] = kwargs.get("env")
                    self.stdout = FakeStdout()
                    self.stderr = FakeStderr()
                    self.returncode = 0

                def poll(self):  # type: ignore[no-untyped-def]
                    return 0

                def kill(self) -> None:
                    return None

            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/yihanc/.local/bin/claude"),
                patch("poco.agent.runner.subprocess.Popen", FakePopen),
                patch(
                    "poco.agent.runner.select.select",
                    side_effect=lambda readers, *_args: ([reader for reader in readers if not getattr(reader, "exhausted", True)], [], []),
                ),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "completed")
            self.assertIn("--permission-mode", captured["command"])
            self.assertIn("bypassPermissions", captured["command"])
            env = captured["env"]
            self.assertIsInstance(env, dict)
            self.assertEqual(env["IS_SANDBOX"], "1")


class CursorAgentRunnerTest(unittest.TestCase):
    def test_cursor_runner_streams_deltas_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CursorAgentRunner(command="cursor-agent", workdir=tmpdir, model="gpt-5")
            task = Task(
                id="cursor_task_stream",
                requester_id="ou_demo",
                prompt="stream output",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="cursor_agent",
            )

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False
                    self._lines = iter(
                        [
                            '{"chatId":"chat_123","type":"session"}\n',
                            '{"textDelta":"Hello"}\n',
                            '{"textDelta":" world"}\n',
                            '{"result":"Hello world","chatId":"chat_123"}\n',
                        ]
                    )

                def readline(self) -> str:
                    line = next(self._lines, "")
                    if not line:
                        self.exhausted = True
                    return line

            class FakeStderr:
                exhausted = True

                def readline(self) -> str:
                    return ""

            class FakePopen:
                def __init__(self) -> None:
                    self.stdout = FakeStdout()
                    self.stderr = FakeStderr()
                    self.returncode = 0
                    self.killed = False

                def poll(self):  # type: ignore[no-untyped-def]
                    return 0 if self.killed or self.stdout.exhausted else None

                def kill(self) -> None:
                    self.killed = True
                    self.returncode = -9

            fake_process = FakePopen()
            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/yihanc/.local/bin/cursor-agent"),
                patch("poco.agent.runner.subprocess.Popen", return_value=fake_process),
                patch(
                    "poco.agent.runner.select.select",
                    side_effect=lambda readers, *_args: ([reader for reader in readers if not getattr(reader, "exhausted", True)], [], []),
                ),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[1].backend_session_id, "chat_123")
            self.assertEqual(updates[2].output_chunk, "Hello")
            self.assertEqual(updates[3].output_chunk, " world")
            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].raw_result, "Hello world")

    def test_cursor_runner_resumes_existing_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CursorAgentRunner(command="cursor-agent", workdir=tmpdir, model="gpt-5")
            task = Task(
                id="cursor_task_resume",
                requester_id="ou_demo",
                prompt="continue",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="cursor_agent",
                backend_session_id="chat_existing",
            )
            captured: dict[str, object] = {}

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False
                    self._lines = iter(
                        [
                            '{"result":"continued","chatId":"chat_existing"}\n',
                        ]
                    )

                def readline(self) -> str:
                    line = next(self._lines, "")
                    if not line:
                        self.exhausted = True
                    return line

            class FakeStderr:
                exhausted = True

                def readline(self) -> str:
                    return ""

            class FakePopen:
                def __init__(self, command, **kwargs):  # type: ignore[no-untyped-def]
                    captured["command"] = command
                    captured["cwd"] = kwargs.get("cwd")
                    self.stdout = FakeStdout()
                    self.stderr = FakeStderr()
                    self.returncode = 0

                def poll(self):  # type: ignore[no-untyped-def]
                    return 0

                def kill(self) -> None:
                    return None

            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/yihanc/.local/bin/cursor-agent"),
                patch("poco.agent.runner.subprocess.Popen", FakePopen),
                patch(
                    "poco.agent.runner.select.select",
                    side_effect=lambda readers, *_args: ([reader for reader in readers if not getattr(reader, "exhausted", True)], [], []),
                ),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[-1].backend_session_id, "chat_existing")
            self.assertIn("--resume", captured["command"])
            self.assertIn("chat_existing", captured["command"])

    def test_cursor_runner_applies_mode_and_sandbox_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CursorAgentRunner(
                command="cursor-agent",
                workdir=tmpdir,
                model="gpt-5",
                mode="default",
                sandbox="default",
            )
            task = Task(
                id="cursor_task_config",
                requester_id="ou_demo",
                prompt="run",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="cursor_agent",
                effective_backend_config={"mode": "plan", "sandbox": "disabled"},
            )
            captured: dict[str, object] = {}

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False
                    self._lines = iter(['{"result":"done","chatId":"chat_config"}\n'])

                def readline(self) -> str:
                    line = next(self._lines, "")
                    if not line:
                        self.exhausted = True
                    return line

            class FakeStderr:
                exhausted = True

                def readline(self) -> str:
                    return ""

            class FakePopen:
                def __init__(self, command, **kwargs):  # type: ignore[no-untyped-def]
                    captured["command"] = command
                    self.stdout = FakeStdout()
                    self.stderr = FakeStderr()
                    self.returncode = 0

                def poll(self):  # type: ignore[no-untyped-def]
                    return 0 if self.stdout.exhausted else None

                def kill(self) -> None:
                    return None

            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/yihanc/.local/bin/cursor-agent"),
                patch("poco.agent.runner.subprocess.Popen", FakePopen),
                patch(
                    "poco.agent.runner.select.select",
                    side_effect=lambda readers, *_args: ([reader for reader in readers if not getattr(reader, "exhausted", True)], [], []),
                ),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "completed")
            self.assertIn("--mode", captured["command"])
            self.assertIn("plan", captured["command"])
            self.assertIn("--sandbox", captured["command"])
            self.assertIn("disabled", captured["command"])


class CocoRunnerTest(unittest.TestCase):
    def test_cleanup_subprocess_closes_pipes_and_waits(self) -> None:
        class FakeStream:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        class FakePopen:
            def __init__(self) -> None:
                self.stdin = FakeStream()
                self.stdout = FakeStream()
                self.stderr = FakeStream()
                self.wait_calls = 0
                self.killed = False

            def wait(self, timeout=None):  # type: ignore[no-untyped-def]
                self.wait_calls += 1
                return 0

            def kill(self) -> None:
                self.killed = True

        process = FakePopen()
        _cleanup_subprocess(process)

        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertTrue(process.stderr.closed)
        self.assertEqual(process.wait_calls, 1)
        self.assertFalse(process.killed)

    def test_coco_runner_streams_updates_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CocoRunner(command="traecli", workdir=tmpdir, model="GPT-5.2")
            task = Task(
                id="coco_task_stream",
                requester_id="ou_demo",
                prompt="stream output",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="coco",
            )
            fake_process = MagicMock()

            class FakeSession:
                def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                    self.prompt_request_id = 99
                    self.reads = iter(
                        [
                            {
                                "method": "session/update",
                                "params": {
                                    "sessionId": "session_123",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "msg_1", "type": "full", "lastChunk": False},
                                        "content": {"type": "text", "text": "Hello"},
                                    },
                                },
                            },
                            {
                                "method": "session/update",
                                "params": {
                                    "sessionId": "session_123",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "msg_1", "type": "full", "lastChunk": False},
                                        "content": {"type": "text", "text": "Hello world"},
                                    },
                                },
                            },
                            {
                                "id": 99,
                                "result": {"stopReason": "end_turn"},
                            },
                        ]
                    )

                def initialize(self) -> None:
                    return None

                def open_session(self, *, session_id: str | None, cwd: str) -> dict[str, object]:
                    return {"sessionId": "session_123"}

                def set_mode(self, *, session_id: str, mode_id: str) -> None:
                    return None

                def set_model(self, *, session_id: str, model_id: str) -> None:
                    return None

                def start_prompt(self, *, session_id: str, prompt: str) -> int:
                    return self.prompt_request_id

                def drain_pending_notifications(self) -> list[dict[str, object]]:
                    return []

                def read_next_message(self) -> dict[str, object] | None:
                    return next(self.reads, None)

                def failure_detail(self, default: str) -> str:
                    return default

            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/bytedance/.local/bin/traecli"),
                patch("poco.agent.runner.subprocess.Popen", return_value=fake_process),
                patch("poco.agent.runner._TraeAcpClient", FakeSession),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[1].backend_session_id, "session_123")
            self.assertEqual(updates[2].output_chunk, "Hello")
            self.assertEqual(updates[3].output_chunk, " world")
            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].backend_session_id, "session_123")
            self.assertEqual(updates[-1].raw_result, "Hello world")

    def test_coco_runner_accumulates_partial_chunks_with_different_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CocoRunner(command="traecli", workdir=tmpdir, model="GPT-5.2")
            task = Task(
                id="coco_task_partial",
                requester_id="ou_demo",
                prompt="hello",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="coco",
            )
            fake_process = MagicMock()

            class FakeSession:
                def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                    self.reads = iter(
                        [
                            {
                                "method": "session/update",
                                "params": {
                                    "sessionId": "session_partial",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "m1", "type": "partial", "lastChunk": False},
                                        "content": {"type": "text", "text": "你"},
                                    },
                                },
                            },
                            {
                                "method": "session/update",
                                "params": {
                                    "sessionId": "session_partial",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "m2", "type": "partial", "lastChunk": False},
                                        "content": {"type": "text", "text": "好"},
                                    },
                                },
                            },
                            {
                                "method": "session/update",
                                "params": {
                                    "sessionId": "session_partial",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "m3", "type": "partial", "lastChunk": False},
                                        "content": {"type": "text", "text": "？"},
                                    },
                                },
                            },
                            {
                                "id": 90,
                                "result": {"stopReason": "end_turn"},
                            },
                        ]
                    )

                def initialize(self) -> None:
                    return None

                def open_session(self, *, session_id: str | None, cwd: str) -> dict[str, object]:
                    return {"sessionId": "session_partial"}

                def set_mode(self, *, session_id: str, mode_id: str) -> None:
                    return None

                def set_model(self, *, session_id: str, model_id: str) -> None:
                    return None

                def start_prompt(self, *, session_id: str, prompt: str) -> int:
                    return 90

                def drain_pending_notifications(self) -> list[dict[str, object]]:
                    return []

                def read_next_message(self) -> dict[str, object] | None:
                    return next(self.reads, None)

                def failure_detail(self, default: str) -> str:
                    return default

            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/bytedance/.local/bin/traecli"),
                patch("poco.agent.runner.subprocess.Popen", return_value=fake_process),
                patch("poco.agent.runner._TraeAcpClient", FakeSession),
            ):
                updates = list(runner.start(task))

            self.assertEqual([u.output_chunk for u in updates if u.output_chunk], ["你", "好", "？"])
            self.assertEqual(updates[-1].raw_result, "你好？")

    def test_coco_runner_loads_existing_session_and_applies_yolo_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CocoRunner(command="traecli", workdir=tmpdir, model="GPT-5.2")
            task = Task(
                id="coco_task_resume",
                requester_id="ou_demo",
                prompt="continue",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="coco",
                backend_session_id="session_existing",
                effective_backend_config={"approval_mode": "yolo"},
            )
            captured: dict[str, object] = {"requests": []}
            fake_process = MagicMock()

            class FakeSession:
                def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                    self.reads = iter(
                        [
                            {
                                "id": 77,
                                "result": {"stopReason": "end_turn"},
                            },
                        ]
                    )

                def initialize(self) -> None:
                    return None

                def open_session(self, *, session_id: str | None, cwd: str) -> dict[str, object]:
                    captured["requests"].append(("session/load", {"sessionId": session_id, "cwd": cwd}))
                    return {"sessionId": "session_existing"}

                def set_mode(self, *, session_id: str, mode_id: str) -> None:
                    captured["requests"].append(("session/set_mode", {"sessionId": session_id, "modeId": mode_id}))

                def set_model(self, *, session_id: str, model_id: str) -> None:
                    captured["requests"].append(("session/set_model", {"sessionId": session_id, "modelId": model_id}))

                def start_prompt(self, *, session_id: str, prompt: str) -> int:
                    captured["prompt"] = ("session/prompt", {"sessionId": session_id, "prompt": prompt})
                    return 77

                def drain_pending_notifications(self) -> list[dict[str, object]]:
                    return []

                def read_next_message(self) -> dict[str, object] | None:
                    return next(self.reads, None)

                def failure_detail(self, default: str) -> str:
                    return default

            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/bytedance/.local/bin/traecli"),
                patch("poco.agent.runner.subprocess.Popen", return_value=fake_process),
                patch("poco.agent.runner._TraeAcpClient", FakeSession),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[-1].backend_session_id, "session_existing")
            requests = captured["requests"]
            self.assertEqual(requests[0][0], "session/load")
            self.assertEqual(requests[0][1]["sessionId"], "session_existing")
            self.assertEqual(requests[1][0], "session/set_mode")
            self.assertEqual(requests[1][1]["modeId"], "bypass_permissions")
            self.assertEqual(requests[2][0], "session/set_model")
            self.assertEqual(requests[2][1]["modelId"], "GPT-5.2")

    def test_coco_runner_ignores_pre_prompt_message_ids_from_loaded_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CocoRunner(command="traecli", workdir=tmpdir, model="GPT-5.2")
            task = Task(
                id="coco_task_history",
                requester_id="ou_demo",
                prompt="new prompt",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="coco",
                backend_session_id="session_existing",
            )
            fake_process = MagicMock()

            class FakeSession:
                def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                    self._pending_notifications = [
                        {
                            "method": "session/update",
                            "params": {
                                "sessionId": "session_existing",
                                "update": {
                                    "sessionUpdate": "agent_message_chunk",
                                    "_meta": {"id": "old_msg", "type": "full", "lastChunk": False},
                                    "content": {"type": "text", "text": "old history"},
                                },
                            },
                        }
                    ]
                    self.reads = iter(
                        [
                            {
                                "method": "session/update",
                                "params": {
                                    "sessionId": "session_existing",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "old_msg", "type": "full", "lastChunk": True},
                                        "content": {"type": "text", "text": "old history continued"},
                                    },
                                },
                            },
                            {
                                "method": "session/update",
                                "params": {
                                    "sessionId": "session_existing",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "new_msg", "type": "full", "lastChunk": True},
                                        "content": {"type": "text", "text": "fresh answer"},
                                    },
                                },
                            },
                            {
                                "id": 88,
                                "result": {"stopReason": "end_turn"},
                            },
                        ]
                    )

                def initialize(self) -> None:
                    return None

                def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
                    if method == "session/load":
                        return {"sessionId": "session_existing"}
                    return {}

                def open_session(self, *, session_id: str | None, cwd: str) -> dict[str, object]:
                    return self.request("session/load", {"sessionId": session_id, "cwd": cwd})

                def set_mode(self, *, session_id: str, mode_id: str) -> None:
                    return None

                def set_model(self, *, session_id: str, model_id: str) -> None:
                    return None

                def start_prompt(self, *, session_id: str, prompt: str) -> int:
                    return 88

                def drain_pending_notifications(self) -> list[dict[str, object]]:
                    drained = list(self._pending_notifications)
                    self._pending_notifications.clear()
                    return drained

                def read_next_message(self) -> dict[str, object] | None:
                    return next(self.reads, None)

                def failure_detail(self, default: str) -> str:
                    return default

            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/bytedance/.local/bin/traecli"),
                patch("poco.agent.runner.subprocess.Popen", return_value=fake_process),
                patch("poco.agent.runner._TraeAcpClient", FakeSession),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual([u.output_chunk for u in updates if u.output_chunk], ["fresh answer"])
            self.assertEqual(updates[-1].raw_result, "fresh answer")

    def test_coco_runner_does_not_complete_on_last_chunk_without_terminal_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CocoRunner(command="traecli", workdir=tmpdir, model="GPT-5.2")
            task = Task(
                id="coco_task_last_chunk",
                requester_id="ou_demo",
                prompt="hello",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="coco",
            )
            fake_process = MagicMock()

            class FakeSession:
                def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                    self.reads = iter(
                        [
                            {
                                "method": "session/update",
                                "params": {
                                    "sessionId": "session_456",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "msg_2", "type": "full", "lastChunk": True},
                                        "content": {"type": "text", "text": "final answer"},
                                    },
                                },
                            },
                        ]
                    )

                def initialize(self) -> None:
                    return None

                def open_session(self, *, session_id: str | None, cwd: str) -> dict[str, object]:
                    return {"sessionId": "session_456"}

                def set_mode(self, *, session_id: str, mode_id: str) -> None:
                    return None

                def set_model(self, *, session_id: str, model_id: str) -> None:
                    return None

                def start_prompt(self, *, session_id: str, prompt: str) -> int:
                    return 88

                def drain_pending_notifications(self) -> list[dict[str, object]]:
                    return []

                def read_next_message(self) -> dict[str, object] | None:
                    return next(self.reads, None)

                def failure_detail(self, default: str) -> str:
                    return default

            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/bytedance/.local/bin/traecli"),
                patch("poco.agent.runner.subprocess.Popen", return_value=fake_process),
                patch("poco.agent.runner._TraeAcpClient", FakeSession),
            ):
                updates = list(runner.start(task))

            self.assertEqual([u.output_chunk for u in updates if u.output_chunk], ["final answer"])
            self.assertEqual(updates[-1].kind, "failed")
            self.assertIn("closed before task completion", updates[-1].message)


if __name__ == "__main__":
    unittest.main()
