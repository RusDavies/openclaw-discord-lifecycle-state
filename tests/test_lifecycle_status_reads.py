import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from openclaw_lifecycle import (
    CurrentChannelContext,
    SafeProjectMapping,
    StateStatusCommand,
    read_channel_registry_lifecycle_state,
    read_lifecycle_state,
    read_mapped_project_lifecycle_state,
)


class LifecycleStatusReadTests(unittest.TestCase):
    def test_reads_mapped_project_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._init_project(tmp, "example")
            self._write_state_file(project, "blocked", "waiting on credentials")

            result = read_mapped_project_lifecycle_state(
                self._channel(),
                self._mapping(project),
                StateStatusCommand(),
                raw_command="state",
            )

            self.assertEqual(result["operation"], "read-status")
            self.assertEqual(result["source_type"], "mapped-project")
            self.assertEqual(result["command"], {"type": "status", "raw": "state"})
            self.assertEqual(result["after"]["state"], "blocked")
            self.assertEqual(result["after"]["reason"], "waiting on credentials")
            self.assertEqual(result["commit_required"], False)

    def test_reads_registry_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            self._write_registry(registry_path, state="paused", reason="until Friday")

            result = read_channel_registry_lifecycle_state(
                self._channel(),
                registry_path,
                StateStatusCommand(),
                raw_command="state status",
            )

            self.assertEqual(result["operation"], "read-status")
            self.assertEqual(result["source_type"], "channel-local-registry")
            self.assertEqual(result["command"], {"type": "status", "raw": "state status"})
            self.assertEqual(result["after"]["state"], "paused")
            self.assertEqual(result["after"]["reason"], "until Friday")
            self.assertEqual(result["commit_required"], False)

    def test_selector_prefers_mapped_project_over_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._init_project(tmp, "example")
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            self._write_state_file(project, "blocked", "mapped state")
            self._write_registry(registry_path, state="paused", reason="registry state")

            result = read_lifecycle_state(
                self._channel(),
                registry_path,
                mapping=self._mapping(project),
                raw_command="state",
            )

            self.assertEqual(result["source_type"], "mapped-project")
            self.assertEqual(result["after"]["state"], "blocked")
            self.assertEqual(result["after"]["reason"], "mapped state")
            self.assertIn("mapped project state takes precedence", result["warnings"][0])
            self.assertEqual(len(result["target_paths"]), 2)

    def test_selector_uses_registry_without_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            self._write_registry(registry_path, state="paused", reason="registry state")

            result = read_lifecycle_state(
                self._channel(),
                registry_path,
                raw_command="state",
            )

            self.assertEqual(result["source_type"], "channel-local-registry")
            self.assertEqual(result["after"]["state"], "paused")

    def test_missing_state_returns_empty_status_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"

            result = read_lifecycle_state(
                self._channel(),
                registry_path,
                raw_command="state",
            )

            self.assertEqual(result["source_type"], "channel-local-registry")
            self.assertIsNone(result["after"])
            self.assertEqual(result["verification"][2]["check"], "state_read")
            self.assertEqual(result["verification"][2]["ok"], False)

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

    def _mapping(self, project: Path) -> SafeProjectMapping:
        return SafeProjectMapping(
            channel_id="111111111111111111",
            project_folder="projects/example",
            project_path=str(project),
            channel_name="example",
        )


if __name__ == "__main__":
    unittest.main()
