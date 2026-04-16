from __future__ import annotations

import subprocess
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

    def test_app_server_runner_completes_from_idle_after_deltas_without_item_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexAppServerRunner(command="codex", workdir=tmpdir)
            task = Task(
                id="task_stream_idle_only",
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

            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].raw_result, "line1\nline2")

    def test_app_server_runner_completes_after_quiet_period_without_terminal_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexAppServerRunner(
                command="codex",
                workdir=tmpdir,
                timeout_seconds=5,
                completion_quiet_seconds=0.0,
            )
            task = Task(
                id="task_stream_quiet_only",
                requester_id="ou_demo",
                prompt="stream output",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
            )

            class FakePopen:
                def poll(self):  # type: ignore[no-untyped-def]
                    return None

                def kill(self) -> None:
                    return None

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
                None,
            ]

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch("poco.agent.runner.subprocess.Popen", return_value=FakePopen()):
                    with patch("poco.agent.runner._CodexAppServerSession", return_value=fake_session):
                        updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].raw_result, "line1\nline2")

    def test_app_server_runner_surfaces_reasoning_progress_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexAppServerRunner(command="codex", workdir=tmpdir)
            task = Task(
                id="task_reasoning",
                requester_id="ou_demo",
                prompt="stream reasoning",
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
                    "method": "item/started",
                    "params": {
                        "threadId": "thread_123",
                        "turnId": "turn_123",
                        "item": {"type": "reasoning", "id": "rs_1"},
                    },
                },
                {
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": "thread_123",
                        "turnId": "turn_123",
                        "tokenUsage": {
                            "last": {"reasoningOutputTokens": 17},
                        },
                    },
                },
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread_123",
                        "turnId": "turn_123",
                        "item": {"type": "agentMessage", "text": "done"},
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

            progress_messages = [update.message for update in updates if update.kind == "progress"]
            self.assertIn("Codex is thinking.", progress_messages)
            self.assertIn("Codex is thinking. reasoning tokens: 17.", progress_messages)
            self.assertEqual(updates[-1].raw_result, "done")

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

    def test_app_server_runner_reuses_transport_for_same_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexAppServerRunner(command="codex", workdir=tmpdir)
            first_task = Task(
                id="task_first",
                requester_id="ou_demo",
                prompt="first prompt",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
            )
            second_task = Task(
                id="task_second",
                requester_id="ou_demo",
                prompt="second prompt",
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
                {"thread": {"id": "thread_first"}},
                {"turn": {"id": "turn_first"}},
                {"thread": {"id": "thread_second"}},
                {"turn": {"id": "turn_second"}},
            ]
            fake_session.read_next_message.side_effect = [
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread_first",
                        "turnId": "turn_first",
                        "item": {"type": "agentMessage", "text": "first answer"},
                    },
                },
                {
                    "method": "thread/status/changed",
                    "params": {
                        "threadId": "thread_first",
                        "status": {"type": "idle"},
                    },
                },
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread_second",
                        "turnId": "turn_second",
                        "item": {"type": "agentMessage", "text": "second answer"},
                    },
                },
                {
                    "method": "thread/status/changed",
                    "params": {
                        "threadId": "thread_second",
                        "status": {"type": "idle"},
                    },
                },
            ]

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch(
                    "poco.agent.runner.subprocess.Popen",
                    side_effect=[FakePopen()],
                ) as popen:
                    with patch("poco.agent.runner._CodexAppServerSession", return_value=fake_session):
                        first_updates = list(runner.start(first_task))
                        second_updates = list(runner.start(second_task))

            self.assertEqual(popen.call_count, 1)
            fake_session.initialize.assert_called_once_with()
            self.assertEqual(first_updates[-1].raw_result, "first answer")
            self.assertEqual(second_updates[-1].raw_result, "second answer")

    def test_app_server_runner_uses_distinct_transport_for_reasoning_effort(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexAppServerRunner(command="codex", workdir=tmpdir)
            first_task = Task(
                id="task_low",
                requester_id="ou_demo",
                prompt="first prompt",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
                effective_backend_config={"reasoning_effort": "low"},
            )
            second_task = Task(
                id="task_medium",
                requester_id="ou_demo",
                prompt="second prompt",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
                effective_backend_config={"reasoning_effort": "medium"},
            )

            class FakePopen:
                def __init__(self) -> None:
                    self.killed = False

                def poll(self):  # type: ignore[no-untyped-def]
                    return 0 if self.killed else None

                def kill(self) -> None:
                    self.killed = True

            low_session = MagicMock()
            low_session.request.side_effect = [
                {"thread": {"id": "thread_low"}},
                {"turn": {"id": "turn_low"}},
            ]
            low_session.read_next_message.side_effect = [
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread_low",
                        "turnId": "turn_low",
                        "item": {"type": "agentMessage", "text": "low answer"},
                    },
                },
                {
                    "method": "thread/status/changed",
                    "params": {
                        "threadId": "thread_low",
                        "status": {"type": "idle"},
                    },
                },
            ]

            medium_session = MagicMock()
            medium_session.request.side_effect = [
                {"thread": {"id": "thread_medium"}},
                {"turn": {"id": "turn_medium"}},
            ]
            medium_session.read_next_message.side_effect = [
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread_medium",
                        "turnId": "turn_medium",
                        "item": {"type": "agentMessage", "text": "medium answer"},
                    },
                },
                {
                    "method": "thread/status/changed",
                    "params": {
                        "threadId": "thread_medium",
                        "status": {"type": "idle"},
                    },
                },
            ]

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch(
                    "poco.agent.runner.subprocess.Popen",
                    side_effect=[FakePopen(), FakePopen()],
                ) as popen:
                    with patch(
                        "poco.agent.runner._CodexAppServerSession",
                        side_effect=[low_session, medium_session],
                    ):
                        low_updates = list(runner.start(first_task))
                        medium_updates = list(runner.start(second_task))

            self.assertEqual(popen.call_count, 2)
            first_command = popen.call_args_list[0].args[0]
            second_command = popen.call_args_list[1].args[0]
            self.assertIn('model_reasoning_effort="low"', first_command)
            self.assertIn('model_reasoning_effort="medium"', second_command)
            self.assertEqual(low_updates[-1].raw_result, "low answer")
            self.assertEqual(medium_updates[-1].raw_result, "medium answer")

    def test_app_server_runner_steers_active_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CodexAppServerRunner(command="codex", workdir=tmpdir)
            task = Task(
                id="task_steer",
                requester_id="ou_demo",
                prompt="stream output",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="codex",
                backend_session_id="thread_123",
            )
            fake_session = MagicMock()
            fake_session.request.return_value = {"turnId": "turn_456"}
            runner._active_turns[task.id] = type("ActiveTurn", (), {  # type: ignore[attr-defined]
                "session": fake_session,
                "thread_id": "thread_123",
                "turn_id": "turn_123",
                "io_lock": __import__("threading").RLock(),
            })()

            success, detail = runner.steer(task, "Please focus on the failing test.")

            self.assertTrue(success)
            self.assertEqual(detail, "Steer sent to Codex.")
            fake_session.request.assert_called_once_with(
                "turn/steer",
                {
                    "threadId": "thread_123",
                    "expectedTurnId": "turn_123",
                    "input": [{"type": "text", "text": "Please focus on the failing test."}],
                },
            )


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
                            '{"type":"control_response","response":{"subtype":"success","request_id":"req_1_deadbeef","response":{"ok":true}}}\n',
                            '{"type":"system","subtype":"init","session_id":"session_123"}\n',
                            '{"type":"stream_event","session_id":"session_123","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}}\n',
                            '{"type":"stream_event","session_id":"session_123","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}}\n',
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

            class FakeStdin:
                def __init__(self) -> None:
                    self.writes: list[str] = []

                def write(self, text: str) -> int:
                    self.writes.append(text)
                    return len(text)

                def flush(self) -> None:
                    return None

                def close(self) -> None:
                    return None

            class FakePopen:
                def __init__(self) -> None:
                    self.stdin = FakeStdin()
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
                patch("poco.agent.runner.os.urandom", return_value=b"\xde\xad\xbe\xef"),
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
                            '{"type":"control_response","response":{"subtype":"success","request_id":"req_1_deadbeef","response":{"ok":true}}}\n',
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

            class FakeStdin:
                def write(self, _text: str) -> int:
                    return 0

                def flush(self) -> None:
                    return None

                def close(self) -> None:
                    return None

            class FakePopen:
                def __init__(self, command, **kwargs):  # type: ignore[no-untyped-def]
                    captured["command"] = command
                    captured["cwd"] = kwargs.get("cwd")
                    self.stdin = FakeStdin()
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
                patch("poco.agent.runner.os.urandom", return_value=b"\xde\xad\xbe\xef"),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[-1].backend_session_id, "session_existing")
            self.assertIn("--resume", captured["command"])
            self.assertIn("session_existing", captured["command"])
            self.assertIn("--input-format", captured["command"])

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
                    self._lines = iter(
                        [
                            '{"type":"control_response","response":{"subtype":"success","request_id":"req_1_deadbeef","response":{"ok":true}}}\n',
                            '{"type":"result","subtype":"success","result":"done","session_id":"session_bypass"}\n',
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

            class FakeStdin:
                def write(self, _text: str) -> int:
                    return 0

                def flush(self) -> None:
                    return None

                def close(self) -> None:
                    return None

            class FakePopen:
                def __init__(self, command, **kwargs):  # type: ignore[no-untyped-def]
                    captured["command"] = command
                    captured["env"] = kwargs.get("env")
                    captured["stdin"] = kwargs.get("stdin")
                    self.stdin = FakeStdin()
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
                patch("poco.agent.runner.os.urandom", return_value=b"\xde\xad\xbe\xef"),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "completed")
            self.assertIn("--permission-mode", captured["command"])
            self.assertIn("bypassPermissions", captured["command"])
            env = captured["env"]
            self.assertIsInstance(env, dict)
            self.assertEqual(env["IS_SANDBOX"], "1")

    def test_claude_runner_injects_anthropic_proxy_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ClaudeCodeRunner(
                command="claude",
                workdir=tmpdir,
                model="sonnet",
            )
            task = Task(
                id="claude_task_proxy_env",
                requester_id="ou_demo",
                prompt="who are you",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="claude_code",
                effective_backend_config={
                    "anthropic_base_url": "http://localhost:8765",
                    "anthropic_api_key": "mira-proxy",
                },
            )
            captured: dict[str, object] = {}

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False
                    self._lines = iter(
                        [
                            '{"type":"control_response","response":{"subtype":"success","request_id":"req_1_deadbeef","response":{"ok":true}}}\n',
                            '{"type":"result","subtype":"success","result":"done","session_id":"session_proxy"}\n',
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

            class FakeStdin:
                def write(self, _text: str) -> int:
                    return 0

                def flush(self) -> None:
                    return None

                def close(self) -> None:
                    return None

            class FakePopen:
                def __init__(self, command, **kwargs):  # type: ignore[no-untyped-def]
                    captured["command"] = command
                    captured["env"] = kwargs.get("env")
                    captured["stdin"] = kwargs.get("stdin")
                    self.stdin = FakeStdin()
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
                patch("poco.agent.runner.os.urandom", return_value=b"\xde\xad\xbe\xef"),
            ):
                updates = list(runner.start(task))

            self.assertEqual(updates[-1].kind, "completed")
            env = captured["env"]
            self.assertIsInstance(env, dict)
            self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://localhost:8765")
            self.assertEqual(env["ANTHROPIC_API_KEY"], "mira-proxy")
            self.assertIs(captured["stdin"], subprocess.PIPE)

    def test_claude_runner_steers_active_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ClaudeCodeRunner(command="claude", workdir=tmpdir, model="sonnet")
            task = Task(
                id="claude_task_steer",
                requester_id="ou_demo",
                prompt="stream output",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="claude_code",
                backend_session_id="session_123",
            )

            class FakeStdin:
                def __init__(self) -> None:
                    self.writes: list[str] = []

                def write(self, text: str) -> int:
                    self.writes.append(text)
                    return len(text)

                def flush(self) -> None:
                    return None

            fake_stdin = FakeStdin()
            runner._active_sessions[task.id] = type("ActiveSession", (), {  # type: ignore[attr-defined]
                "process": None,
                "stdin": fake_stdin,
                "session_id": "session_123",
                "io_lock": __import__("threading").RLock(),
                "pending_controls": {},
                "next_request_id": 0,
                "ignored_result_count": 0,
            })()

            with patch.object(runner, "_send_claude_control_request", return_value={}):
                success, detail = runner.steer(task, "Focus on the failing test first.")

            self.assertTrue(success)
            self.assertEqual(detail, "Steer sent to Claude Code.")
            self.assertEqual(len(fake_stdin.writes), 1)
            self.assertIn('"type": "user"', fake_stdin.writes[0])
            self.assertIn('"session_id": "session_123"', fake_stdin.writes[0])
            self.assertIn("Focus on the failing test first.", fake_stdin.writes[0])


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

    def test_cursor_runner_handles_assistant_message_events_and_terminal_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CursorAgentRunner(command="cursor-agent", workdir=tmpdir, model="gpt-5")
            task = Task(
                id="cursor_task_new_protocol",
                requester_id="ou_demo",
                prompt="say hi",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="cursor_agent",
            )

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False
                    self._lines = iter(
                        [
                            '{"type":"system","subtype":"init","session_id":"session_abc"}\n',
                            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"hello"}]},"session_id":"session_abc"}\n',
                            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"。\\n\\n"}]},"session_id":"session_abc"}\n',
                            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"world"}]},"session_id":"session_abc"}\n',
                            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"。"}]},"session_id":"session_abc"}\n',
                            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"hello。\\n\\nworld。"}]},"session_id":"session_abc"}\n',
                            '{"type":"result","subtype":"success","is_error":false,"result":"hello。\\n\\nworld。","session_id":"session_abc"}\n',
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
                    return None

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

            self.assertEqual(updates[1].backend_session_id, "session_abc")
            self.assertEqual(
                [u.output_chunk for u in updates if u.output_chunk],
                ["hello", "。\n\n", "world", "。"],
            )
            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].raw_result, "hello。\n\nworld。")

    def test_cursor_runner_completes_on_result_without_waiting_for_process_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CursorAgentRunner(command="cursor-agent", workdir=tmpdir, model="gpt-5")
            task = Task(
                id="cursor_task_result_exit",
                requester_id="ou_demo",
                prompt="say hi",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="cursor_agent",
            )

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False
                    self._lines = iter(
                        [
                            '{"type":"result","subtype":"success","is_error":false,"result":"hi","session_id":"session_wait"}\n',
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

                def poll(self):  # type: ignore[no-untyped-def]
                    return None

                def kill(self) -> None:
                    return None

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

            self.assertEqual(updates[1].backend_session_id, "session_wait")
            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].raw_result, "hi")

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

    def test_cursor_runner_maps_legacy_model_and_sandbox_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CursorAgentRunner(
                command="cursor-agent",
                workdir=tmpdir,
                model="gpt-5",
                mode="default",
                sandbox="workspace-write",
            )
            task = Task(
                id="cursor_task_legacy_config",
                requester_id="ou_demo",
                prompt="run",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="cursor_agent",
                effective_backend_config={"mode": "default", "sandbox": "workspace-write"},
            )
            captured: dict[str, object] = {}

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False
                    self._lines = iter(['{"type":"result","subtype":"success","is_error":false,"result":"done","session_id":"chat_legacy"}\n'])

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
                    return None

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
            self.assertIn("--model", captured["command"])
            self.assertIn("auto", captured["command"])
            self.assertIn("--sandbox", captured["command"])
            self.assertIn("enabled", captured["command"])

    def test_cursor_runner_surfaces_terminal_error_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CursorAgentRunner(command="cursor-agent", workdir=tmpdir, model="gpt-5")
            task = Task(
                id="cursor_task_error",
                requester_id="ou_demo",
                prompt="broken",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="cursor_agent",
            )

            class FakeStdout:
                def __init__(self) -> None:
                    self.exhausted = False
                    self._lines = iter(
                        [
                            '{"type":"result","subtype":"error","is_error":true,"error":{"message":"runner crashed"},"session_id":"session_err"}\n',
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
                    self.returncode = 1

                def poll(self):  # type: ignore[no-untyped-def]
                    return 1 if self.stdout.exhausted else None

                def kill(self) -> None:
                    return None

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

            self.assertEqual(updates[-1].kind, "failed")
            self.assertEqual(updates[-1].message, "runner crashed")


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

    def test_coco_runner_preserves_whitespace_in_partial_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CocoRunner(command="traecli", workdir=tmpdir, model="GPT-5.2")
            task = Task(
                id="coco_task_whitespace",
                requester_id="ou_demo",
                prompt="format text",
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
                                    "sessionId": "session_whitespace",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "m1", "type": "partial", "lastChunk": False},
                                        "content": {"type": "text", "text": "cpp\n"},
                                    },
                                },
                            },
                            {
                                "method": "session/update",
                                "params": {
                                    "sessionId": "session_whitespace",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "m2", "type": "partial", "lastChunk": False},
                                        "content": {"type": "text", "text": "#include <iostream>\n"},
                                    },
                                },
                            },
                            {
                                "method": "session/update",
                                "params": {
                                    "sessionId": "session_whitespace",
                                    "update": {
                                        "sessionUpdate": "agent_message_chunk",
                                        "_meta": {"id": "m3", "type": "partial", "lastChunk": False},
                                        "content": {"type": "text", "text": "int main() {\n  return 0;\n}\n"},
                                    },
                                },
                            },
                            {
                                "id": 91,
                                "result": {"stopReason": "end_turn"},
                            },
                        ]
                    )

                def initialize(self) -> None:
                    return None

                def open_session(self, *, session_id: str | None, cwd: str) -> dict[str, object]:
                    return {"sessionId": "session_whitespace"}

                def set_mode(self, *, session_id: str, mode_id: str) -> None:
                    return None

                def set_model(self, *, session_id: str, model_id: str) -> None:
                    return None

                def start_prompt(self, *, session_id: str, prompt: str) -> int:
                    return 91

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

            self.assertEqual(
                [u.output_chunk for u in updates if u.output_chunk],
                ["cpp\n", "#include <iostream>\n", "int main() {\n  return 0;\n}\n"],
            )
            self.assertEqual(
                updates[-1].raw_result,
                "cpp\n#include <iostream>\nint main() {\n  return 0;\n}",
            )

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

    def test_coco_runner_reuses_warm_transport_for_same_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CocoRunner(command="traecli", workdir=tmpdir, model="GPT-5.2")
            first_task = Task(
                id="coco_task_first",
                requester_id="ou_demo",
                prompt="first",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="coco",
            )
            second_task = Task(
                id="coco_task_second",
                requester_id="ou_demo",
                prompt="second",
                source="feishu",
                status=TaskStatus.RUNNING,
                agent_backend="coco",
            )
            fake_process = MagicMock()
            fake_process.poll.return_value = None
            captured = {
                "initialize_calls": 0,
                "start_prompt_calls": 0,
                "instances": 0,
            }

            class FakeSession:
                def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                    captured["instances"] += 1
                    self._reads: list[dict[str, object]] = []

                def initialize(self) -> None:
                    captured["initialize_calls"] += 1

                def open_session(self, *, session_id: str | None, cwd: str) -> dict[str, object]:
                    return {"sessionId": "session_reused"}

                def set_mode(self, *, session_id: str, mode_id: str) -> None:
                    return None

                def set_model(self, *, session_id: str, model_id: str) -> None:
                    return None

                def start_prompt(self, *, session_id: str, prompt: str) -> int:
                    captured["start_prompt_calls"] += 1
                    request_id = captured["start_prompt_calls"]
                    self._reads = [
                        {
                            "method": "session/update",
                            "params": {
                                "sessionId": "session_reused",
                                "update": {
                                    "sessionUpdate": "agent_message_chunk",
                                    "_meta": {"id": f"msg_{request_id}", "type": "partial", "lastChunk": False},
                                    "content": {"type": "text", "text": f"reply {request_id}"},
                                },
                            },
                        },
                        {
                            "id": request_id,
                            "result": {"stopReason": "end_turn"},
                        },
                    ]
                    return request_id

                def drain_pending_notifications(self) -> list[dict[str, object]]:
                    return []

                def read_next_message(self) -> dict[str, object] | None:
                    if not self._reads:
                        return None
                    return self._reads.pop(0)

                def failure_detail(self, default: str) -> str:
                    return default

            with (
                patch("poco.agent.runner.shutil.which", return_value="/Users/bytedance/.local/bin/traecli"),
                patch("poco.agent.runner.subprocess.Popen", return_value=fake_process) as popen,
                patch("poco.agent.runner._TraeAcpClient", FakeSession),
            ):
                first_updates = list(runner.start(first_task))
                second_updates = list(runner.start(second_task))

            self.assertEqual(popen.call_count, 1)
            self.assertEqual(captured["instances"], 1)
            self.assertEqual(captured["initialize_calls"], 1)
            self.assertEqual(first_updates[-1].raw_result, "reply 1")
            self.assertEqual(second_updates[-1].raw_result, "reply 2")


if __name__ == "__main__":
    unittest.main()
