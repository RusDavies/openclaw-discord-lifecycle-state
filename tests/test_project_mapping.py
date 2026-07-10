import tempfile
import unittest
from pathlib import Path

from openclaw_lifecycle import (
    CurrentChannelContext,
    ProjectMappingError,
    SafeProjectMapping,
    resolve_safe_project_mapping,
)


def channel_index(*entries):
    return {
        "schema": "openclaw.discord_channel_index.v1",
        "entries": list(entries),
    }


class SafeProjectMappingTests(unittest.TestCase):
    def test_resolves_exact_channel_id_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = CurrentChannelContext(
                channel_id="111111111111111111",
                channel_name="openclaw-project-lifecycle-state",
            )
            mapping = resolve_safe_project_mapping(
                context,
                channel_index(
                    {
                        "kind": "mapping",
                        "target_id": "111111111111111111",
                        "labels": ["#openclaw-project-lifecycle-state"],
                        "project_folders": ["projects/openclaw-project-lifecycle-state"],
                        "github_remotes": [
                            "example/openclaw-project-lifecycle-state"
                        ],
                    }
                ),
                workspace_root=tmp,
            )

            self.assertEqual(
                mapping,
                SafeProjectMapping(
                    channel_id="111111111111111111",
                    project_folder="projects/openclaw-project-lifecycle-state",
                    project_path=str(
                        Path(tmp)
                        / "projects"
                        / "openclaw-project-lifecycle-state"
                    ),
                    channel_name="openclaw-project-lifecycle-state",
                    github_remotes=(
                        "example/openclaw-project-lifecycle-state",
                    ),
                ),
            )

    def test_returns_none_for_unknown_channel(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        self.assertIsNone(resolve_safe_project_mapping(context, channel_index()))

    def test_returns_none_for_known_unmapped_channel(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        self.assertIsNone(
            resolve_safe_project_mapping(
                context,
                channel_index(
                    {
                        "kind": "mapping",
                        "target_id": "111111111111111111",
                        "labels": ["#loose-channel"],
                        "project_folders": [],
                    }
                ),
            )
        )

    def test_uses_index_label_when_context_name_missing(self):
        context = CurrentChannelContext(channel_id="111111111111111111")
        mapping = resolve_safe_project_mapping(
            context,
            channel_index(
                {
                    "kind": "mapping",
                    "target_id": "111111111111111111",
                    "labels": ["#mapped-name"],
                    "project_folders": ["projects/mapped-name"],
                }
            ),
        )

        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.channel_name, "mapped-name")

    def test_rejects_ambiguous_channel_matches(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        with self.assertRaises(ProjectMappingError):
            resolve_safe_project_mapping(
                context,
                channel_index(
                    {
                        "kind": "mapping",
                        "target_id": "111111111111111111",
                        "project_folders": ["projects/one"],
                    },
                    {
                        "kind": "mapping",
                        "target_id": "111111111111111111",
                        "project_folders": ["projects/two"],
                    },
                ),
            )

    def test_rejects_multiple_project_folders(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        with self.assertRaises(ProjectMappingError):
            resolve_safe_project_mapping(
                context,
                channel_index(
                    {
                        "kind": "mapping",
                        "target_id": "111111111111111111",
                        "project_folders": ["projects/one", "projects/two"],
                    }
                ),
            )

    def test_rejects_absolute_project_folder(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        with self.assertRaises(ProjectMappingError):
            resolve_safe_project_mapping(
                context,
                channel_index(
                    {
                        "kind": "mapping",
                        "target_id": "111111111111111111",
                        "project_folders": ["/tmp/project"],
                    }
                ),
            )

    def test_rejects_project_folder_outside_projects(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        with self.assertRaises(ProjectMappingError):
            resolve_safe_project_mapping(
                context,
                channel_index(
                    {
                        "kind": "mapping",
                        "target_id": "111111111111111111",
                        "project_folders": ["../outside"],
                    }
                ),
            )

    def test_rejects_non_list_entries(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        with self.assertRaises(ProjectMappingError):
            resolve_safe_project_mapping(context, {"entries": "not-a-list"})


if __name__ == "__main__":
    unittest.main()
