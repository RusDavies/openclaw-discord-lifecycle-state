import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from openclaw_lifecycle import (
    CurrentChannelContext,
    MigrateStateHereCommand,
    SafeProjectMapping,
    StateMigrationError,
    StateMigrationOptions,
    format_state_migration_response,
    migrate_registry_state_to_project,
)


class StateMigrationTests(unittest.TestCase):
    def test_migrates_registry_entry_to_project_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._init_project(root)
            registry_path = root / "data" / "channel-lifecycle-state.json"
            self._write_registry(registry_path)

            result = migrate_registry_state_to_project(
                self._channel(),
                self._mapping(project),
                MigrateStateHereCommand(),
                self._options(registry_path),
            )

            state_file = project / "LIFECYCLE_STATE.md"
            state_text = state_file.read_text(encoding="utf-8")
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            entry = registry["channels"]["123"]

            self.assertEqual(result["operation"], "migrate-registry-state")
            self.assertEqual(result["after"]["project"]["state"], "paused")
            self.assertEqual(result["after"]["project"]["since"], "2026-07-10")
            self.assertIn("source: registry-migration", state_text)
            self.assertIn("reason: \"until Friday\"", state_text)
            self.assertEqual(entry["mapping_status"], "mapped-shadow")
            self.assertEqual(entry["mapped_project"], "projects/demo")
            self.assertIn("Project commit required.", format_state_migration_response(result))

    def test_requires_safe_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            self._write_registry(registry_path)

            with self.assertRaises(StateMigrationError):
                migrate_registry_state_to_project(
                    self._channel(),
                    None,
                    MigrateStateHereCommand(),
                    self._options(registry_path),
                )

    def test_requires_registry_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._init_project(root)
            registry_path = root / "data" / "channel-lifecycle-state.json"
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "schema": "openclaw.lifecycle.channel_registry.v1",
                        "version": 1,
                        "updated_at": "",
                        "channels": {},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(StateMigrationError):
                migrate_registry_state_to_project(
                    self._channel(),
                    self._mapping(project),
                    MigrateStateHereCommand(),
                    self._options(registry_path),
                )

    def test_dry_run_does_not_write_project_or_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._init_project(root)
            registry_path = root / "data" / "channel-lifecycle-state.json"
            self._write_registry(registry_path)

            result = migrate_registry_state_to_project(
                self._channel(),
                self._mapping(project),
                MigrateStateHereCommand(),
                StateMigrationOptions(
                    actor="Lifecycle Bot",
                    now=datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc),
                    registry_path=registry_path,
                    raw_command="migrate state here",
                    dry_run=True,
                ),
            )

            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertTrue(result["dry_run"])
            self.assertFalse((project / "LIFECYCLE_STATE.md").exists())
            self.assertEqual(registry["channels"]["123"]["mapping_status"], "unmapped")

    def _init_project(self, root: Path) -> Path:
        project = root / "projects" / "demo"
        project.mkdir(parents=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=project, check=True, stdout=subprocess.PIPE)
        return project

    def _write_registry(self, registry_path: Path) -> None:
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            json.dumps(
                {
                    "schema": "openclaw.lifecycle.channel_registry.v1",
                    "version": 1,
                    "updated_at": "2026-07-10T12:00:00+00:00",
                    "channels": {
                        "123": {
                            "channel_id": "123",
                            "state": "paused",
                            "since": "2026-07-10",
                            "updated_at": "2026-07-10T12:00:00+00:00",
                            "updated_by": "Example User",
                            "reason": "until Friday",
                            "source": "discord-command",
                            "mapping_status": "unmapped",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def _channel(self) -> CurrentChannelContext:
        return CurrentChannelContext(channel_id="123", channel_name="demo")

    def _mapping(self, project: Path) -> SafeProjectMapping:
        return SafeProjectMapping(
            channel_id="123",
            project_folder="projects/demo",
            project_path=str(project),
            channel_name="demo",
        )

    def _options(self, registry_path: Path) -> StateMigrationOptions:
        return StateMigrationOptions(
            actor="Lifecycle Bot",
            now=datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc),
            registry_path=registry_path,
            raw_command="migrate state here",
        )


if __name__ == "__main__":
    unittest.main()
