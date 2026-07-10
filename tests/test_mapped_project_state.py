import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from openclaw_lifecycle import (
    CurrentChannelContext,
    MappedProjectStateError,
    MappedProjectWriteOptions,
    SafeProjectMapping,
    StateSetCommand,
    write_mapped_project_lifecycle_state,
)


class MappedProjectStateWriteTests(unittest.TestCase):
    def test_writes_new_mapped_project_lifecycle_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._init_project(tmp, "example")
            channel = self._channel()
            mapping = self._mapping(project)

            result = write_mapped_project_lifecycle_state(
                channel,
                mapping,
                StateSetCommand(
                    state="blocked",
                    reason="waiting on credentials",
                ),
                MappedProjectWriteOptions(
                    actor="Example Operator",
                    raw_command="state blocked waiting on credentials",
                    now=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
                ),
            )

            state_file = project / "LIFECYCLE_STATE.md"
            self.assertTrue(state_file.exists())
            self.assertEqual(result["ok"], True)
            self.assertEqual(result["source_type"], "mapped-project")
            self.assertEqual(result["commit_required"], True)
            self.assertIsNone(result["before"])
            self.assertEqual(result["after"]["state"], "blocked")
            self.assertEqual(result["after"]["reason"], "waiting on credentials")
            self.assertEqual(result["project"]["git_top_level"], str(project))
            self.assertEqual(result["target_paths"], [str(state_file)])

            content = state_file.read_text(encoding="utf-8")
            self.assertIn("state: blocked", content)
            self.assertIn("since: 2026-07-10", content)
            self.assertIn('channel_id: "111111111111111111"', content)
            self.assertIn('updated_by: "Example Operator"', content)
            self.assertIn('reason: "waiting on credentials"', content)
            self.assertIn("source: discord-command", content)
            self.assertIn("updated_at: 2026-07-10T08:00:00+00:00", content)
            self.assertIn('mapped_project: "projects/example"', content)

    def test_preserves_since_and_unknown_fields_when_state_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._init_project(tmp, "example")
            state_file = project / "LIFECYCLE_STATE.md"
            state_file.write_text(
                "\n".join(
                    [
                        "# Lifecycle State",
                        "",
                        "state: blocked",
                        "since: 2026-07-08",
                        'channel_id: "111111111111111111"',
                        'updated_by: "Lifecycle Bot"',
                        'reason: "waiting on access"',
                        "source: discord-command",
                        "next_review: 2026-07-15",
                        'custom_note: "keep this"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = write_mapped_project_lifecycle_state(
                self._channel(),
                self._mapping(project),
                StateSetCommand(
                    state="blocked",
                    reason="waiting on credentials",
                ),
                MappedProjectWriteOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
                ),
            )

            content = state_file.read_text(encoding="utf-8")
            self.assertEqual(result["before"]["state"], "blocked")
            self.assertEqual(result["before"]["since"], "2026-07-08")
            self.assertEqual(result["after"]["since"], "2026-07-08")
            self.assertIn("since: 2026-07-08", content)
            self.assertIn("next_review: 2026-07-15", content)
            self.assertIn('custom_note: "keep this"', content)
            self.assertIn('reason: "waiting on credentials"', content)

    def test_resets_since_when_state_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._init_project(tmp, "example")
            (project / "LIFECYCLE_STATE.md").write_text(
                "\n".join(
                    [
                        "# Lifecycle State",
                        "",
                        "state: active",
                        "since: 2026-07-01",
                        'channel_id: "111111111111111111"',
                        'updated_by: "Lifecycle Bot"',
                        'reason: "current work"',
                        "source: discord-command",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = write_mapped_project_lifecycle_state(
                self._channel(),
                self._mapping(project),
                StateSetCommand(
                    state="blocked",
                    reason="waiting on credentials",
                ),
                MappedProjectWriteOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
                ),
            )

            self.assertEqual(result["before"]["since"], "2026-07-01")
            self.assertEqual(result["after"]["since"], "2026-07-10")
            self.assertIn(
                "since: 2026-07-10",
                (project / "LIFECYCLE_STATE.md").read_text(encoding="utf-8"),
            )

    def test_rejects_project_outside_its_git_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            project = root / "projects" / "example"
            project.mkdir(parents=True)

            with self.assertRaises(MappedProjectStateError):
                write_mapped_project_lifecycle_state(
                    self._channel(),
                    self._mapping(project),
                    StateSetCommand(state="active", reason=""),
                    MappedProjectWriteOptions(
                        actor="Lifecycle Bot",
                        now=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
                    ),
                )

    def test_dry_run_returns_packet_without_writing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._init_project(tmp, "example")

            result = write_mapped_project_lifecycle_state(
                self._channel(),
                self._mapping(project),
                StateSetCommand(state="active", reason=""),
                MappedProjectWriteOptions(
                    actor="Lifecycle Bot",
                    now=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
                    dry_run=True,
                ),
            )

            self.assertEqual(result["dry_run"], True)
            self.assertEqual(result["commit_required"], False)
            self.assertFalse((project / "LIFECYCLE_STATE.md").exists())

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

    def _mapping(self, project: Path) -> SafeProjectMapping:
        return SafeProjectMapping(
            channel_id="111111111111111111",
            project_folder="projects/example",
            project_path=str(project),
            channel_name="example",
            github_remotes=("example/example",),
        )


if __name__ == "__main__":
    unittest.main()
