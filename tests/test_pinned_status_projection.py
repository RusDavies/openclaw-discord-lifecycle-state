import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from openclaw_lifecycle import (
    CurrentChannelContext,
    ManagedDiscordMessage,
    PinLifecycleStatusCommand,
    PinnedStatusApplyCallables,
    PinnedStatusProjectionError,
    PinnedStatusProjectionOptions,
    SafeProjectMapping,
    format_pinned_status_message,
    handle_pinned_status_projection,
    parse_pin_lifecycle_status_command,
)


class PinnedStatusProjectionTests(unittest.TestCase):
    def test_parses_dry_run_and_apply_commands(self):
        self.assertEqual(
            parse_pin_lifecycle_status_command("pin lifecycle status"),
            PinLifecycleStatusCommand(apply=False),
        )
        self.assertEqual(
            parse_pin_lifecycle_status_command("pin lifecycle status dry-run"),
            PinLifecycleStatusCommand(apply=False),
        )
        self.assertEqual(
            parse_pin_lifecycle_status_command("lifecycle status pin apply"),
            PinLifecycleStatusCommand(apply=True),
        )

    def test_formats_managed_status_message_from_mapped_state(self):
        message = format_pinned_status_message(
            {
                "source_type": "mapped-project",
                "after": {
                    "state": "pending-approval",
                    "reason": "Ready for review",
                    "since": "2026-07-10",
                    "updated_at": "2026-07-10T12:00:00+00:00",
                },
            }
        )

        self.assertEqual(
            message,
            "\n".join(
                [
                    "Lifecycle: pending-approval",
                    "Reason: Ready for review",
                    "Since: 2026-07-10",
                    "Updated: 2026-07-10T12:00:00+00:00",
                    "Source: mapped project LIFECYCLE_STATE.md",
                    "Managed by OpenClaw lifecycle projection.",
                ]
            ),
        )

    def test_dry_run_returns_send_and_pin_actions_without_registry_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._init_project(root)
            self._write_state_file(project)
            registry_path = root / "data" / "lifecycle-pinned-status-messages.json"

            result = handle_pinned_status_projection(
                self._channel(),
                self._mapping(project),
                root / "data" / "channel-lifecycle-state.json",
                PinnedStatusProjectionOptions(
                    now=datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc),
                    registry_path=registry_path,
                    workspace_root=root,
                    raw_command="pin lifecycle status dry-run",
                    dry_run=True,
                ),
            )

            self.assertTrue(result["dry_run"])
            self.assertFalse(registry_path.exists())
            self.assertEqual(
                [action["action"] for action in result["proposed_external_actions"]],
                ["send", "pin"],
            )
            self.assertIn(
                "Managed by OpenClaw lifecycle projection.",
                result["proposed_external_actions"][0]["message"],
            )

    def test_apply_sends_pins_and_records_managed_message_id_outside_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._init_project(root)
            self._write_state_file(project)
            projection_registry = root / "data" / "lifecycle-pinned-status-messages.json"
            receipts: list[tuple[str, str]] = []

            result = handle_pinned_status_projection(
                self._channel(),
                self._mapping(project),
                root / "data" / "channel-lifecycle-state.json",
                PinnedStatusProjectionOptions(
                    now=datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc),
                    registry_path=projection_registry,
                    workspace_root=root,
                    raw_command="pin lifecycle status apply",
                    dry_run=False,
                ),
                apply_callables=PinnedStatusApplyCallables(
                    send_message=lambda message: receipts.append(("send", message))
                    or {"messageId": "555"},
                    pin_message=lambda message_id: receipts.append(("pin", message_id))
                    or {"pinned": True},
                    edit_message=lambda message_id, message: {"edited": True},
                    fetch_message=lambda message_id: None,
                ),
            )

            registry = json.loads(projection_registry.read_text(encoding="utf-8"))
            state_text = (project / "LIFECYCLE_STATE.md").read_text(encoding="utf-8")
            self.assertFalse(result["dry_run"])
            self.assertEqual(result["applied"]["message_id"], "555")
            self.assertEqual(receipts[0][0], "send")
            self.assertEqual(receipts[1], ("pin", "555"))
            self.assertEqual(registry["channels"]["123"]["message_id"], "555")
            self.assertNotIn("555", state_text)

    def test_apply_refuses_to_edit_unmanaged_existing_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._init_project(root)
            self._write_state_file(project)
            projection_registry = root / "data" / "lifecycle-pinned-status-messages.json"
            projection_registry.parent.mkdir(parents=True)
            projection_registry.write_text(
                json.dumps(
                    {
                        "schema": "openclaw.lifecycle.pinned_status_registry.v1",
                        "version": 1,
                        "updated_at": "2026-07-16T10:00:00+00:00",
                        "channels": {"123": {"channel_id": "123", "message_id": "555"}},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(PinnedStatusProjectionError):
                handle_pinned_status_projection(
                    self._channel(),
                    self._mapping(project),
                    root / "data" / "channel-lifecycle-state.json",
                    PinnedStatusProjectionOptions(
                        now=datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc),
                        registry_path=projection_registry,
                        workspace_root=root,
                        raw_command="pin lifecycle status apply",
                        dry_run=False,
                    ),
                    apply_callables=PinnedStatusApplyCallables(
                        send_message=lambda message: {"messageId": "999"},
                        pin_message=lambda message_id: {"pinned": True},
                        edit_message=lambda message_id, message: {"edited": True},
                        fetch_message=lambda message_id: ManagedDiscordMessage(
                            message_id=message_id,
                            author_is_bot=True,
                            content="some other bot message",
                        ),
                    ),
                )

    def _init_project(self, root: Path) -> Path:
        project = root / "projects" / "demo"
        project.mkdir(parents=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=project, check=True, stdout=subprocess.PIPE)
        return project

    def _write_state_file(self, project: Path) -> None:
        (project / "LIFECYCLE_STATE.md").write_text(
            "\n".join(
                [
                    "# Lifecycle State",
                    "",
                    "state: pending-approval",
                    "since: 2026-07-10",
                    'channel_id: "123"',
                    'updated_by: "Lifecycle Bot"',
                    'reason: "Ready for review"',
                    "source: discord-command",
                    "updated_at: 2026-07-10T12:00:00+00:00",
                    "",
                ]
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


if __name__ == "__main__":
    unittest.main()
