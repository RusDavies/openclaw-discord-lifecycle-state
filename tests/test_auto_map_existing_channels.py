from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import auto_map_existing_channels as automap  # noqa: E402


class AutoMapExistingChannelsTests(unittest.TestCase):
    def test_matches_unmapped_decorated_channel_to_existing_project_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            projects = root / "projects"
            (projects / "remembah").mkdir(parents=True)
            index = self.write_json(root / "index.json", {"entries": []})
            snapshot = self.write_json(
                root / "snapshot.json",
                {
                    "channels": [
                        {
                            "id": "1504103414165016678",
                            "name": "🟡-remembah",
                            "parent_category_name": "Approval",
                            "type": 0,
                        }
                    ]
                },
            )

            with mock.patch.object(automap, "github_remote", return_value="example/remembah"):
                candidates = automap.build_candidates(
                    index_path=index,
                    snapshot_path=snapshot,
                    projects_root=projects,
                    workspace_root=root,
                )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].channel_name, "remembah")
        self.assertEqual(candidates[0].project_folder, "projects/remembah")
        self.assertIn("project folder `projects/remembah`", candidates[0].map_line())
        self.assertIn("GitHub remote `example/remembah`", candidates[0].map_line())

    def test_skips_already_mapped_channel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            projects = root / "projects"
            (projects / "remembah").mkdir(parents=True)
            index = self.write_json(
                root / "index.json",
                {
                    "entries": [
                        {
                            "kind": "mapping",
                            "target_id": "1",
                            "project_folders": ["projects/remembah"],
                        }
                    ]
                },
            )
            snapshot = self.write_json(
                root / "snapshot.json",
                {"channels": [{"id": "1", "name": "remembah", "type": 0}]},
            )

            candidates = automap.build_candidates(
                index_path=index,
                snapshot_path=snapshot,
                projects_root=projects,
                workspace_root=root,
            )

        self.assertEqual(candidates, [])

    def test_append_mappings_adds_auto_mapped_section_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            map_path = Path(temp_dir) / "discord-channel-map.md"
            map_path.write_text("# Discord Channel Map\n", encoding="utf-8")
            candidate = automap.MappingCandidate(
                channel_id="1",
                channel_name="remembah",
                project_folder="projects/remembah",
                github_remote="example/remembah",
                parent_category_name="Approval",
            )

            automap.append_mappings(map_path, [candidate])
            automap.append_mappings(map_path, [candidate])

            content = map_path.read_text(encoding="utf-8")

        self.assertEqual(content.count("## Auto-Mapped Existing Project Channels"), 1)
        self.assertEqual(content.count("`#remembah` → `1`"), 2)

    def write_json(self, path: Path, data: dict[str, object]) -> Path:
        path.write_text(json.dumps(data), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
