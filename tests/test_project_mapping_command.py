import json
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from openclaw_lifecycle import (
    CurrentChannelContext,
    MapProjectHereCommand,
    MapProjectHereError,
    MapProjectHereOptions,
    format_map_project_here_response,
    map_project_here,
)


class MapProjectHereTests(unittest.TestCase):
    def test_maps_existing_channel_row_to_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._init_project(root, "demo", remote="example/demo")
            map_path, index_path, registry_path = self._write_map(
                root,
                "- `#demo` -> `123` (old arrow ignored)\n",
            )
            map_path.write_text("- `#demo` → `123` (test channel)\n", encoding="utf-8")
            self._write_index(index_path, map_path)

            result = map_project_here(
                CurrentChannelContext(channel_id="123", channel_name="demo"),
                MapProjectHereCommand(project="demo"),
                self._options(root, map_path, index_path, registry_path),
            )

            self.assertTrue(project.exists())
            self.assertTrue(result["map"]["changed"])
            self.assertIn(
                "project folder `projects/demo`",
                map_path.read_text(encoding="utf-8"),
            )
            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(index["entries"][0]["project_folders"], ["projects/demo"])
            self.assertEqual(result["project"]["github_remote"], "example/demo")

    def test_maps_new_channel_when_no_row_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_project(root, "demo")
            map_path, index_path, registry_path = self._write_map(root, "")

            result = map_project_here(
                CurrentChannelContext(channel_id="123", channel_name="demo"),
                MapProjectHereCommand(project="projects/demo"),
                self._options(root, map_path, index_path, registry_path),
            )

            self.assertTrue(result["map"]["changed"])
            self.assertIn(
                "- `#demo` → `123` (project folder `projects/demo`",
                map_path.read_text(encoding="utf-8"),
            )

    def test_already_mapped_to_same_project_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_project(root, "demo")
            map_path, index_path, registry_path = self._write_map(
                root,
                "- `#demo` → `123` (project folder `projects/demo`)\n",
            )

            result = map_project_here(
                CurrentChannelContext(channel_id="123", channel_name="demo"),
                MapProjectHereCommand(project="projects/demo"),
                self._options(root, map_path, index_path, registry_path),
            )

            self.assertFalse(result["map"]["changed"])
            self.assertFalse(result["commit_required"])
            self.assertIn("already mapped", format_map_project_here_response(result))

    def test_rejects_conflicting_existing_project_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_project(root, "demo")
            map_path, index_path, registry_path = self._write_map(
                root,
                "- `#demo` → `123` (project folder `projects/other`)\n",
            )

            with self.assertRaises(MapProjectHereError):
                map_project_here(
                    CurrentChannelContext(channel_id="123", channel_name="demo"),
                    MapProjectHereCommand(project="projects/demo"),
                    self._options(root, map_path, index_path, registry_path),
                )

    def test_reports_existing_registry_entry_without_migrating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_project(root, "demo")
            map_path, index_path, registry_path = self._write_map(
                root,
                "- `#demo` → `123` (test channel)\n",
            )
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "schema": "openclaw.lifecycle.channel_registry.v1",
                        "version": 1,
                        "updated_at": "2026-07-10T12:00:00+00:00",
                        "channels": {"123": {"state": "paused", "reason": "waiting"}},
                    }
                ),
                encoding="utf-8",
            )

            result = map_project_here(
                CurrentChannelContext(channel_id="123", channel_name="demo"),
                MapProjectHereCommand(project="projects/demo"),
                self._options(root, map_path, index_path, registry_path),
            )

            self.assertTrue(result["registry"]["entry_exists"])
            self.assertEqual(result["registry"]["state"], "paused")
            self.assertIn("migration", format_map_project_here_response(result))

    def _init_project(self, root: Path, name: str, remote: str = "") -> Path:
        project = root / "projects" / name
        project.mkdir(parents=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=project, check=True, stdout=subprocess.PIPE)
        if remote:
            subprocess.run(
                ["git", "remote", "add", "origin", f"https://github.com/{remote}.git"],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
            )
        return project

    def _write_map(self, root: Path, content: str) -> tuple[Path, Path, Path]:
        map_path = root / "agent-operating-details" / "discord-channel-map.md"
        index_path = root / "agent-operating-details" / "discord-channel-index.json"
        registry_path = root / "data" / "channel-lifecycle-state.json"
        map_path.parent.mkdir(parents=True)
        map_path.write_text(content, encoding="utf-8")
        self._write_index(index_path, map_path)
        return map_path, index_path, registry_path

    def _write_index(self, index_path: Path, map_path: Path) -> None:
        entries = []
        for line_number, raw in enumerate(map_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.startswith("- "):
                continue
            entries.append(
                {
                    "kind": "mapping",
                    "line": line_number,
                    "raw": raw,
                    "target_id": "123",
                    "labels": ["#demo"],
                    "project_folders": (
                        ["projects/demo"] if "project folder `projects/demo`" in raw else
                        ["projects/other"] if "project folder `projects/other`" in raw else []
                    ),
                    "github_remotes": [],
                }
            )
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps({"entries": entries}), encoding="utf-8")

    def _options(
        self,
        root: Path,
        map_path: Path,
        index_path: Path,
        registry_path: Path,
    ) -> MapProjectHereOptions:
        return MapProjectHereOptions(
            workspace_root=root,
            map_path=map_path,
            index_path=index_path,
            registry_path=registry_path,
            today=date(2026, 7, 14),
        )


if __name__ == "__main__":
    unittest.main()
