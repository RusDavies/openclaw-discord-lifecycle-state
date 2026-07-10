import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from openclaw_lifecycle import (
    CurrentChannelContext,
    LifecycleWorkflowOptions,
    format_state_status_response,
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

    def test_unmapped_channel_write_command_updates_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            result = handle_lifecycle_command(
                "state paused until Friday",
                self._channel(),
                self._unmapped_lookup_packet(),
                LifecycleWorkflowOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    registry_path=registry_path,
                    workspace_root=tmp,
                ),
            )

            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            entry = registry["channels"]["111111111111111111"]
            self.assertEqual(result["source_type"], "channel-local-registry")
            self.assertEqual(result["operation"], "write-state")
            self.assertEqual(result["command"]["raw"], "state paused until Friday")
            self.assertEqual(result["after"]["state"], "paused")
            self.assertEqual(result["after"]["reason"], "until Friday")
            self.assertEqual(result["commit_required"], False)
            self.assertEqual(entry["state"], "paused")
            self.assertEqual(entry["reason"], "until Friday")
            self.assertEqual(entry["mapping_status"], "unmapped")

    def test_unmapped_channel_write_command_formats_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = handle_lifecycle_command(
                "state paused until Friday",
                self._channel(),
                self._unmapped_lookup_packet(),
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
                        "State updated: `paused`",
                        "Reason: until Friday",
                        "Stored: channel-local registry",
                    ]
                ),
            )

    def test_mapped_channel_status_command_reads_project_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._init_project(tmp, "example")
            self._write_state_file(project, "blocked", "waiting on credentials")
            result = handle_lifecycle_command(
                "state status",
                self._channel(),
                self._mapped_lookup_packet(),
                LifecycleWorkflowOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    registry_path=Path(tmp) / "data" / "channel-lifecycle-state.json",
                    workspace_root=tmp,
                ),
            )

            self.assertEqual(result["source_type"], "mapped-project")
            self.assertEqual(result["operation"], "read-status")
            self.assertEqual(result["command"], {"type": "status", "raw": "state status"})
            self.assertEqual(result["after"]["state"], "blocked")
            self.assertEqual(result["after"]["reason"], "waiting on credentials")
            self.assertEqual(result["after"]["since"], "2026-07-10")
            self.assertEqual(result["commit_required"], False)
            self.assertEqual(result["target_paths"], [str(project / "LIFECYCLE_STATE.md")])

    def test_mapped_channel_status_command_formats_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._init_project(tmp, "example")
            self._write_state_file(project, "ktlo", "routine maintenance")
            result = handle_lifecycle_command(
                "state",
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
                format_state_status_response(result),
                "\n".join(
                    [
                        "State: `ktlo`",
                        "Reason: routine maintenance",
                        "Since: 2026-07-10",
                        "Updated: 2026-07-10T12:00:00+00:00",
                        "Source: mapped project `LIFECYCLE_STATE.md`",
                    ]
                ),
            )

    def test_unmapped_channel_status_command_reads_registry_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            self._write_registry(registry_path, state="paused", reason="until Friday")
            result = handle_lifecycle_command(
                "state status",
                self._channel(),
                self._unmapped_lookup_packet(),
                LifecycleWorkflowOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    registry_path=registry_path,
                    workspace_root=tmp,
                ),
            )

            self.assertEqual(result["source_type"], "channel-local-registry")
            self.assertEqual(result["operation"], "read-status")
            self.assertEqual(result["command"], {"type": "status", "raw": "state status"})
            self.assertEqual(result["after"]["state"], "paused")
            self.assertEqual(result["after"]["reason"], "until Friday")
            self.assertEqual(result["after"]["since"], "2026-07-10")
            self.assertEqual(result["commit_required"], False)
            self.assertEqual(result["target_paths"], [str(registry_path)])

    def test_unmapped_channel_status_command_formats_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            self._write_registry(registry_path, state="spike", reason="testing options")
            result = handle_lifecycle_command(
                "state",
                self._channel(),
                self._unmapped_lookup_packet(),
                LifecycleWorkflowOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    registry_path=registry_path,
                    workspace_root=tmp,
                ),
            )

            self.assertEqual(
                format_state_status_response(result),
                "\n".join(
                    [
                        "State: `spike`",
                        "Reason: testing options",
                        "Since: 2026-07-10",
                        "Updated: 2026-07-10T12:00:00+00:00",
                        "Source: channel-local registry",
                    ]
                ),
            )

    def _init_project(self, tmp: str, name: str) -> Path:
        project = Path(tmp) / "projects" / name
        project.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        return project.resolve()

    def _write_state_file(self, project: Path, state: str, reason: str) -> None:
        (project / "LIFECYCLE_STATE.md").write_text(
            "\n".join(
                [
                    "# Lifecycle State",
                    "",
                    f"state: {state}",
                    "since: 2026-07-10",
                    'channel_id: "111111111111111111"',
                    'updated_by: "Lifecycle Bot"',
                    f'reason: "{reason}"',
                    "source: discord-command",
                    "updated_at: 2026-07-10T12:00:00+00:00",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _write_registry(self, registry_path: Path, *, state: str, reason: str) -> None:
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            json.dumps(
                {
                    "schema": "openclaw.lifecycle.channel_registry.v1",
                    "version": 1,
                    "updated_at": "2026-07-10T12:00:00+00:00",
                    "channels": {
                        "111111111111111111": {
                            "channel_id": "111111111111111111",
                            "state": state,
                            "since": "2026-07-10",
                            "updated_at": "2026-07-10T12:00:00+00:00",
                            "updated_by": "Lifecycle Bot",
                            "reason": reason,
                            "source": "discord-command",
                            "mapping_status": "unmapped",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

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

    def _unmapped_lookup_packet(self) -> dict:
        return {
            "schema": "openclaw.lifecycle.channel_lookup_adapter.v1",
            "status": "unmapped",
            "channel_id": "111111111111111111",
        }


if __name__ == "__main__":
    unittest.main()
