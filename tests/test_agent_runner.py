from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from poco.agent.runner import CodexCliRunner
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
                        stream_lines=["step 1\n", "step 2\n"],
                    ),
                ):
                    updates = list(runner.start(task))

            self.assertEqual(updates[1].kind, "progress")
            self.assertEqual(updates[1].output_chunk, "step 1\n")
            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].result_summary, "codex final answer")

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


if __name__ == "__main__":
    unittest.main()
