import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from openclaw_lifecycle import (
    ChannelRegistryStateError,
    ChannelRegistryWriteOptions,
    CurrentChannelContext,
    StateSetCommand,
    write_channel_registry_lifecycle_state,
)


class ChannelRegistryStateWriteTests(unittest.TestCase):
    def test_writes_new_channel_registry_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"

            result = write_channel_registry_lifecycle_state(
                self._channel(),
                registry_path,
                StateSetCommand(
                    state="paused",
                    reason="until Friday",
                ),
                ChannelRegistryWriteOptions(
                    actor="Example Operator",
                    raw_command="state paused until Friday",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                ),
            )

            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            entry = registry["channels"]["111111111111111111"]
            self.assertEqual(registry["schema"], "openclaw.lifecycle.channel_registry.v1")
            self.assertEqual(registry["version"], 1)
            self.assertEqual(registry["updated_at"], "2026-07-10T12:00:00+00:00")
            self.assertEqual(entry["channel_id"], "111111111111111111")
            self.assertEqual(entry["state"], "paused")
            self.assertEqual(entry["since"], "2026-07-10")
            self.assertEqual(entry["updated_at"], "2026-07-10T12:00:00+00:00")
            self.assertEqual(entry["updated_by"], "Example Operator")
            self.assertEqual(entry["reason"], "until Friday")
            self.assertEqual(entry["source"], "discord-command")
            self.assertEqual(entry["mapping_status"], "unmapped")
            self.assertEqual(entry["channel_name"], "loose-channel")
            self.assertEqual(entry["guild_id"], "222222222222222222")

            self.assertEqual(result["ok"], True)
            self.assertEqual(result["source_type"], "channel-local-registry")
            self.assertEqual(result["commit_required"], False)
            self.assertIsNone(result["before"])
            self.assertEqual(result["after"]["state"], "paused")
            self.assertEqual(result["registry"]["entry_key"], "111111111111111111")
            self.assertEqual(result["target_paths"], [str(registry_path)])

    def test_preserves_since_and_other_channels_when_state_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "schema": "openclaw.lifecycle.channel_registry.v1",
                        "version": 1,
                        "updated_at": "2026-07-09T12:00:00+00:00",
                        "channels": {
                            "111111111111111111": {
                                "channel_id": "111111111111111111",
                                "state": "paused",
                                "since": "2026-07-08",
                                "updated_at": "2026-07-09T12:00:00+00:00",
                                "updated_by": "Lifecycle Bot",
                                "reason": "waiting",
                                "source": "discord-command",
                                "mapping_status": "unmapped",
                                "history": [
                                    {
                                        "state": "active",
                                        "changed_at": "2026-07-07T12:00:00+00:00",
                                        "changed_by": "Lifecycle Bot",
                                        "reason": "current work",
                                        "source": "discord-command",
                                    }
                                ],
                            },
                            "1523767147816288407": {
                                "channel_id": "1523767147816288407",
                                "state": "active",
                                "since": "2026-07-09",
                                "updated_at": "2026-07-09T12:00:00+00:00",
                                "updated_by": "Lifecycle Bot",
                                "reason": "other channel",
                                "source": "discord-command",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = write_channel_registry_lifecycle_state(
                self._channel(),
                registry_path,
                StateSetCommand(
                    state="paused",
                    reason="until Friday",
                ),
                ChannelRegistryWriteOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                ),
            )

            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            entry = registry["channels"]["111111111111111111"]
            self.assertEqual(result["before"]["since"], "2026-07-08")
            self.assertEqual(result["after"]["since"], "2026-07-08")
            self.assertEqual(entry["since"], "2026-07-08")
            self.assertEqual(entry["reason"], "until Friday")
            self.assertEqual(entry["history"][0]["state"], "active")
            self.assertIn("1523767147816288407", registry["channels"])

    def test_resets_since_when_state_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "schema": "openclaw.lifecycle.channel_registry.v1",
                        "version": 1,
                        "updated_at": "2026-07-09T12:00:00+00:00",
                        "channels": {
                            "111111111111111111": {
                                "channel_id": "111111111111111111",
                                "state": "active",
                                "since": "2026-07-01",
                                "updated_at": "2026-07-09T12:00:00+00:00",
                                "updated_by": "Lifecycle Bot",
                                "reason": "current work",
                                "source": "discord-command",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = write_channel_registry_lifecycle_state(
                self._channel(),
                registry_path,
                StateSetCommand(
                    state="blocked",
                    reason="waiting on credentials",
                ),
                ChannelRegistryWriteOptions(
                    actor="Example Operator",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                ),
            )

            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            entry = registry["channels"]["111111111111111111"]
            self.assertEqual(result["before"]["since"], "2026-07-01")
            self.assertEqual(result["after"]["since"], "2026-07-10")
            self.assertEqual(entry["since"], "2026-07-10")

    def test_dry_run_returns_packet_without_writing_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"

            result = write_channel_registry_lifecycle_state(
                self._channel(),
                registry_path,
                StateSetCommand(state="active", reason=""),
                ChannelRegistryWriteOptions(
                    actor="Lifecycle Bot",
                    now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    dry_run=True,
                ),
            )

            self.assertEqual(result["dry_run"], True)
            self.assertEqual(result["commit_required"], False)
            self.assertFalse(registry_path.exists())

    def test_rejects_invalid_registry_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "data" / "channel-lifecycle-state.json"
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text("{not json", encoding="utf-8")

            with self.assertRaises(ChannelRegistryStateError):
                write_channel_registry_lifecycle_state(
                    self._channel(),
                    registry_path,
                    StateSetCommand(state="active", reason=""),
                    ChannelRegistryWriteOptions(
                        actor="Lifecycle Bot",
                        now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    ),
                )

    def _channel(self) -> CurrentChannelContext:
        return CurrentChannelContext(
            channel_id="111111111111111111",
            channel_name="loose-channel",
            guild_id="222222222222222222",
            guild_name="Example Workspace",
            category_id="1497330993382555659",
            category_name="Active",
        )


if __name__ == "__main__":
    unittest.main()
