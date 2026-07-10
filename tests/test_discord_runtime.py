import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from openclaw_lifecycle import (
    CurrentChannelContext,
    DiscordRuntimeOptions,
    handle_discord_state_command,
    normalize_channel_lookup_response,
)


class DiscordRuntimeAdapterTests(unittest.TestCase):
    def test_normalizes_mapped_channel_lookup_response(self):
        packet = normalize_channel_lookup_response(
            CurrentChannelContext(
                channel_id="111111111111111111",
                channel_name="openclaw-project-lifecycle-state",
            ),
            self._mapped_lookup_response(),
        )

        self.assertEqual(packet["status"], "mapped")
        self.assertEqual(packet["channel_id"], "111111111111111111")
        self.assertEqual(
            packet["mapping"]["project_folder"],
            "projects/openclaw-project-lifecycle-state",
        )
        self.assertEqual(
            packet["mapping"]["github_remotes"],
            ["example/openclaw-project-lifecycle-state"],
        )

    def test_normalizes_missing_project_folder_as_unmapped(self):
        packet = normalize_channel_lookup_response(
            CurrentChannelContext(channel_id="111111111111111111"),
            {
                "count": 1,
                "matches": [
                    {
                        "channelId": "111111111111111111",
                        "names": ["#loose-channel"],
                        "notes": "No project folder here.",
                    }
                ],
            },
        )

        self.assertEqual(packet["status"], "unmapped")

    def test_runtime_mapped_write_sends_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "openclaw-project-lifecycle-state"
            project.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
            sent: list[str] = []
            looked_up: list[str] = []

            result = handle_discord_state_command(
                "state blocked waiting on credentials",
                self._conversation_info(),
                self._channel_metadata(),
                lambda channel_id: self._record_lookup(
                    looked_up,
                    channel_id,
                    self._mapped_lookup_response(),
                ),
                lambda message: sent.append(message) or {"sent": True},
                DiscordRuntimeOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    registry_path=Path(tmp) / "data" / "channel-lifecycle-state.json",
                    workspace_root=tmp,
                ),
            )

            self.assertEqual(looked_up, ["111111111111111111"])
            self.assertEqual(result["ok"], True)
            self.assertEqual(result["result"]["source_type"], "mapped-project")
            self.assertEqual(
                sent,
                [
                    "\n".join(
                        [
                            "State updated: `blocked`",
                            "Reason: waiting on credentials",
                            "Stored: mapped project `LIFECYCLE_STATE.md`",
                            "Project commit required.",
                        ]
                    )
                ],
            )
            self.assertIn(
                "state: blocked",
                (project / "LIFECYCLE_STATE.md").read_text(encoding="utf-8"),
            )

    def test_runtime_unmapped_write_sends_registry_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            sent: list[str] = []

            result = handle_discord_state_command(
                "state paused until Friday",
                self._conversation_info(),
                self._channel_metadata(),
                lambda channel_id: {"count": 0, "matches": []},
                lambda message: sent.append(message),
                DiscordRuntimeOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    registry_path=registry_path,
                    workspace_root=tmp,
                ),
            )

            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(result["ok"], True)
            self.assertEqual(result["lookup_packet"]["status"], "unmapped")
            self.assertEqual(
                registry["channels"]["111111111111111111"]["state"],
                "paused",
            )
            self.assertEqual(
                sent,
                [
                    "\n".join(
                        [
                            "State updated: `paused`",
                            "Reason: until Friday",
                            "Stored: channel-local registry",
                        ]
                    )
                ],
            )

    def test_runtime_invalid_state_sends_visible_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            sent: list[str] = []

            result = handle_discord_state_command(
                "state waiting on vendor",
                self._conversation_info(),
                self._channel_metadata(),
                lambda channel_id: {"count": 0, "matches": []},
                lambda message: sent.append(message),
                DiscordRuntimeOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    registry_path=Path(tmp) / "data" / "channel-lifecycle-state.json",
                    workspace_root=tmp,
                ),
            )

            self.assertEqual(result["ok"], False)
            self.assertIn("Invalid lifecycle state 'waiting'.", sent[0])
            self.assertIn("Allowed states:", sent[0])

    def test_runtime_lookup_blocker_does_not_append_allowed_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            sent: list[str] = []

            result = handle_discord_state_command(
                "state active",
                self._conversation_info(),
                self._channel_metadata(),
                lambda channel_id: {
                    "count": 2,
                    "matches": [
                        {"channelId": "111111111111111111"},
                        {"channelId": "111111111111111111"},
                    ],
                },
                lambda message: sent.append(message),
                DiscordRuntimeOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    registry_path=Path(tmp) / "data" / "channel-lifecycle-state.json",
                    workspace_root=tmp,
                ),
            )

            self.assertEqual(result["ok"], False)
            self.assertEqual(
                sent,
                ["Cannot safely resolve lifecycle storage source: ambiguous"],
            )

    def _record_lookup(self, calls: list[str], channel_id: str, response: dict) -> dict:
        calls.append(channel_id)
        return response

    def _mapped_lookup_response(self) -> dict:
        return {
            "count": 1,
            "matches": [
                {
                    "lineNumber": 46,
                    "names": ["#openclaw-project-lifecycle-state"],
                    "channelId": "111111111111111111",
                    "notes": (
                        "Example Workspace Active project channel; project folder "
                        "`projects/openclaw-project-lifecycle-state`; GitHub remote "
                        "`example/openclaw-project-lifecycle-state`"
                    ),
                    "raw": (
                        "- `#openclaw-project-lifecycle-state` -> "
                        "`111111111111111111` (project folder "
                        "`projects/openclaw-project-lifecycle-state`; GitHub remote "
                        "`example/openclaw-project-lifecycle-state`)"
                    ),
                }
            ],
        }

    def _conversation_info(self) -> dict:
        return {
            "chat_id": "channel:111111111111111111",
            "group_channel": "#openclaw-project-lifecycle-state",
            "group_space": "222222222222222222",
        }

    def _channel_metadata(self) -> dict:
        return {
            "source": "discord",
            "type": "channel_metadata",
            "payload": {"topic": "Lifecycle project channel."},
        }


if __name__ == "__main__":
    unittest.main()
