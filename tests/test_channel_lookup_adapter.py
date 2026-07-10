import tempfile
import unittest
from pathlib import Path

from openclaw_lifecycle import (
    ChannelLookupPacketError,
    ChannelLookupResolution,
    CurrentChannelContext,
    ProjectMappingError,
    SafeProjectMapping,
    resolve_channel_lookup_packet,
)


class ChannelLookupAdapterTests(unittest.TestCase):
    def test_resolves_mapped_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = CurrentChannelContext(
                channel_id="111111111111111111",
                channel_name="openclaw-project-lifecycle-state",
            )
            result = resolve_channel_lookup_packet(
                context,
                {
                    "schema": "openclaw.lifecycle.channel_lookup_adapter.v1",
                    "status": "mapped",
                    "channel_id": "111111111111111111",
                    "mapping": {
                        "channel_id": "111111111111111111",
                        "channel_name": "openclaw-project-lifecycle-state",
                        "project_folder": "projects/openclaw-project-lifecycle-state",
                        "github_remotes": [
                            "example/openclaw-project-lifecycle-state"
                        ],
                    },
                },
                workspace_root=tmp,
            )

            self.assertEqual(
                result,
                ChannelLookupResolution(
                    status="mapped",
                    mapping=SafeProjectMapping(
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
                ),
            )

    def test_returns_unmapped_resolution(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        result = resolve_channel_lookup_packet(
            context,
            {
                "schema": "openclaw.lifecycle.channel_lookup_adapter.v1",
                "status": "unmapped",
                "channel_id": "111111111111111111",
            },
        )

        self.assertEqual(result, ChannelLookupResolution(status="unmapped"))

    def test_returns_ambiguous_resolution_with_errors(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        result = resolve_channel_lookup_packet(
            context,
            {
                "schema": "openclaw.lifecycle.channel_lookup_adapter.v1",
                "status": "ambiguous",
                "channel_id": "111111111111111111",
                "errors": ["channel_lookup returned multiple matches"],
            },
        )

        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(result.errors, ("channel_lookup returned multiple matches",))
        self.assertIsNone(result.mapping)

    def test_returns_error_resolution_with_errors(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        result = resolve_channel_lookup_packet(
            context,
            {
                "schema": "openclaw.lifecycle.channel_lookup_adapter.v1",
                "status": "error",
                "channel_id": "111111111111111111",
                "errors": ["channel_lookup tool unavailable"],
            },
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.errors, ("channel_lookup tool unavailable",))
        self.assertIsNone(result.mapping)

    def test_rejects_mapped_packet_without_mapping(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        with self.assertRaises(ChannelLookupPacketError):
            resolve_channel_lookup_packet(
                context,
                {
                    "schema": "openclaw.lifecycle.channel_lookup_adapter.v1",
                    "status": "mapped",
                    "channel_id": "111111111111111111",
                },
            )

    def test_rejects_non_mapped_packet_with_mapping(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        with self.assertRaises(ChannelLookupPacketError):
            resolve_channel_lookup_packet(
                context,
                {
                    "schema": "openclaw.lifecycle.channel_lookup_adapter.v1",
                    "status": "unmapped",
                    "channel_id": "111111111111111111",
                    "mapping": {
                        "channel_id": "111111111111111111",
                        "project_folder": "projects/not-used",
                    },
                },
            )

    def test_rejects_channel_mismatch(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        with self.assertRaises(ChannelLookupPacketError):
            resolve_channel_lookup_packet(
                context,
                {
                    "schema": "openclaw.lifecycle.channel_lookup_adapter.v1",
                    "status": "unmapped",
                    "channel_id": "999999999999999999",
                },
            )

    def test_rejects_unsafe_project_folder(self):
        context = CurrentChannelContext(channel_id="111111111111111111")

        with self.assertRaises(ProjectMappingError):
            resolve_channel_lookup_packet(
                context,
                {
                    "schema": "openclaw.lifecycle.channel_lookup_adapter.v1",
                    "status": "mapped",
                    "channel_id": "111111111111111111",
                    "mapping": {
                        "channel_id": "111111111111111111",
                        "project_folder": "../outside",
                    },
                },
            )


if __name__ == "__main__":
    unittest.main()
