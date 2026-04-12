from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from poco.agent.runner import ClaudeCodeRunner, CodexAppServerRunner, CodexCliRunner
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
                patch("poco.agent.runner.select.select", side_effect=lambda readers, *_args: (readers, [], [])),
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
                    self._lines = iter(
                        [
                            '{"type":"result","subtype":"success","result":"continued","session_id":"session_existing"}\n',
                        ]
                    )

                def readline(self) -> str:
                    return next(self._lines, "")

            class FakeStderr:
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
                patch("poco.agent.runner.select.select", side_effect=lambda readers, *_args: (readers, [], [])),
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
                def readline(self) -> str:
                    return '{"type":"result","subtype":"success","result":"done","session_id":"session_bypass"}\n'

            class FakeStderr:
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
                patch("poco.agent.runner.select.select", side_effect=lambda readers, *_args: (readers, [], [])),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "completed")
            self.assertIn("--permission-mode", captured["command"])
            self.assertIn("bypassPermissions", captured["command"])
            env = captured["env"]
            self.assertIsInstance(env, dict)
            self.assertEqual(env["IS_SANDBOX"], "1")


if __name__ == "__main__":
    unittest.main()
