import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from openclaw_lifecycle import (
    CurrentChannelContext,
    LifecycleWorkflowOptions,
    format_state_write_confirmation,
    handle_lifecycle_command,
)


class LifecycleCommandWorkflowTests(unittest.TestCase):
    def test_mapped_channel_write_command_updates_project_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._init_project(tmp, "example")
            result = handle_lifecycle_command(
                "state blocked waiting on credentials",
                self._channel(),
                self._mapped_lookup_packet(),
                LifecycleWorkflowOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    registry_path=Path(tmp) / "data" / "channel-lifecycle-state.json",
                    workspace_root=tmp,
                ),
            )

            state_file = project / "LIFECYCLE_STATE.md"
            self.assertEqual(result["source_type"], "mapped-project")
            self.assertEqual(result["operation"], "write-state")
            self.assertEqual(result["command"]["raw"], "state blocked waiting on credentials")
            self.assertEqual(result["after"]["state"], "blocked")
            self.assertEqual(result["after"]["reason"], "waiting on credentials")
            self.assertEqual(result["commit_required"], True)
            self.assertTrue(state_file.exists())
            self.assertFalse((Path(tmp) / "data" / "channel-lifecycle-state.json").exists())
            self.assertIn(
                'reason: "waiting on credentials"',
                state_file.read_text(encoding="utf-8"),
            )

    def test_mapped_channel_write_command_formats_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_project(tmp, "example")
            result = handle_lifecycle_command(
                "state active current implementation work",
                self._channel(),
                self._mapped_lookup_packet(),
                LifecycleWorkflowOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    registry_path=Path(tmp) / "data" / "channel-lifecycle-state.json",
                    workspace_root=tmp,
                ),
            )

            self.assertEqual(
                format_state_write_confirmation(result),
                "\n".join(
                    [
                        "State updated: `active`",
                        "Reason: current implementation work",
                        "Stored: mapped project `LIFECYCLE_STATE.md`",
                        "Project commit required.",
                    ]
                ),
            )

    def _init_project(self, tmp: str, name: str) -> Path:
        project = Path(tmp) / "projects" / name
        project.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        return project.resolve()

    def _channel(self) -> CurrentChannelContext:
        return CurrentChannelContext(
            channel_id="111111111111111111",
            channel_name="example",
            guild_id="222222222222222222",
        )

    def _mapped_lookup_packet(self) -> dict:
        return {
            "schema": "openclaw.lifecycle.channel_lookup_adapter.v1",
            "status": "mapped",
            "channel_id": "111111111111111111",
            "mapping": {
                "channel_id": "111111111111111111",
                "channel_name": "example",
                "project_folder": "projects/example",
                "github_remotes": ["example/example"],
            },
        }


if __name__ == "__main__":
    unittest.main()
