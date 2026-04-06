from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from poco.agent.runner import CodexCliRunner
from poco.task.models import Task, TaskStatus


class CodexCliRunnerTest(unittest.TestCase):
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
        updates = runner.start(task)
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

            def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
                output_index = command.index("-o") + 1
                Path(command[output_index]).write_text("codex final answer", encoding="utf-8")

                class Result:
                    returncode = 0
                    stdout = "stdout"
                    stderr = ""

                return Result()

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch("poco.agent.runner.subprocess.run", side_effect=fake_run):
                    updates = runner.start(task)

            self.assertEqual(updates[-1].kind, "completed")
            self.assertEqual(updates[-1].result_summary, "codex final answer")

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

            class Result:
                returncode = 1
                stdout = ""
                stderr = "codex failed"

            with patch("poco.agent.runner.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch("poco.agent.runner.subprocess.run", return_value=Result()):
                    updates = runner.start(task)

            self.assertEqual(updates[-1].kind, "failed")
            self.assertIn("codex failed", updates[-1].message)


if __name__ == "__main__":
    unittest.main()
