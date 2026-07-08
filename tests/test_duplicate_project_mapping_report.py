from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import duplicate_project_mapping_report as duplicate_report  # noqa: E402


class DuplicateProjectMappingReportTests(unittest.TestCase):
    def test_distinguishes_duplicate_rows_from_multi_channel_projects(self) -> None:
        index_path = self.index(
            [
                self.mapping("1", "projects/alpha", ["#alpha"]),
                self.mapping("1", "projects/alpha", ["The Bubble #alpha"]),
                self.mapping("2", "projects/bravo", ["#bravo"]),
                self.mapping("3", "projects/bravo", ["#bravo-dev"]),
            ]
        )

        report = duplicate_report.build_report(index_path, resolution_config_path=None)
        by_project = {item.project_folder: item for item in report}

        self.assertEqual(by_project["projects/alpha"].classification, "duplicate-index-row")
        self.assertEqual(by_project["projects/alpha"].distinct_channel_ids, ("1",))
        self.assertEqual(by_project["projects/bravo"].classification, "multi-channel-project")
        self.assertEqual(by_project["projects/bravo"].distinct_channel_ids, ("2", "3"))

    def test_json_summary_counts_duplicate_types(self) -> None:
        duplicates = [
            duplicate_report.DuplicateProjectMapping(
                project_folder="projects/alpha",
                entries=(
                    duplicate_report.MappingEntry("1", ("#alpha",), (), ""),
                    duplicate_report.MappingEntry("1", ("#alpha",), (), ""),
                ),
            ),
            duplicate_report.DuplicateProjectMapping(
                project_folder="projects/bravo",
                entries=(
                    duplicate_report.MappingEntry("2", ("#bravo",), (), ""),
                    duplicate_report.MappingEntry("3", ("#bravo-dev",), (), ""),
                ),
            ),
        ]

        data = duplicate_report.json_data(
            duplicates,
            index_path=PROJECT_ROOT / "index.json",
            resolution_config_path=None,
        )

        self.assertEqual(data["summary"]["duplicate_project_folders"], 2)
        self.assertEqual(data["summary"]["duplicate_mapping_rows"], 4)
        self.assertEqual(data["summary"]["multi_channel_project_folders"], 1)
        self.assertEqual(data["summary"]["duplicate_index_row_groups"], 1)
        self.assertEqual(data["summary"]["resolved_duplicate_groups"], 0)
        self.assertEqual(data["summary"]["unresolved_duplicate_groups"], 1)
        self.assertEqual(data["summary"]["index_hygiene_duplicate_groups"], 1)

    def test_configured_canonical_channel_marks_duplicate_resolved(self) -> None:
        index_path = self.index(
            [
                self.mapping("1", "projects/alpha", ["#alpha"]),
                self.mapping("2", "projects/alpha", ["#alpha-dev"]),
            ]
        )
        resolutions_path = self.resolutions(
            [
                {
                    "project_folder": "projects/alpha",
                    "canonical_channel_id": "1",
                    "decision_reason": "main channel",
                }
            ]
        )

        report = duplicate_report.build_report(
            index_path,
            resolution_config_path=resolutions_path,
        )

        self.assertEqual(report[0].resolution_status, "resolved")
        self.assertEqual(report[0].recommendation, "Use the configured canonical channel for lifecycle seeding.")

    def test_invalid_configured_canonical_channel_is_flagged(self) -> None:
        item = duplicate_report.DuplicateProjectMapping(
            project_folder="projects/alpha",
            entries=(
                duplicate_report.MappingEntry("1", ("#alpha",), (), ""),
                duplicate_report.MappingEntry("2", ("#alpha-dev",), (), ""),
            ),
            canonical_channel_id="3",
        )

        self.assertEqual(item.resolution_status, "invalid-canonical-channel")

    def mapping(self, channel_id: str, project_folder: str, labels: list[str]) -> dict[str, object]:
        return {
            "kind": "mapping",
            "target_id": channel_id,
            "labels": labels,
            "project_folders": [project_folder],
            "github_remotes": [],
            "notes": "",
        }

    def index(self, entries: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        )
        self.addCleanup(lambda path=handle.name: Path(path).unlink(missing_ok=True))
        with handle:
            json.dump({"entries": entries}, handle)
        return Path(handle.name)

    def resolutions(self, entries: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        )
        self.addCleanup(lambda path=handle.name: Path(path).unlink(missing_ok=True))
        with handle:
            json.dump(
                {
                    "schema": "openclaw.lifecycle.canonical_project_channels.v1",
                    "canonical_project_channels": entries,
                },
                handle,
            )
        return Path(handle.name)


if __name__ == "__main__":
    unittest.main()
