import unittest

from openclaw_lifecycle import (
    LifecycleCommandError,
    LifecycleResponseError,
    format_lifecycle_command_error,
    format_state_status_response,
    format_state_write_confirmation,
    parse_state_set_command,
)


class DiscordResponseFormattingTests(unittest.TestCase):
    def test_formats_mapped_project_write_confirmation(self):
        message = format_state_write_confirmation(
            {
                "ok": True,
                "operation": "write-state",
                "source_type": "mapped-project",
                "before": {
                    "state": "active",
                    "reason": "current work",
                    "source": "discord-command",
                },
                "after": {
                    "state": "blocked",
                    "reason": "waiting on credentials",
                    "source": "discord-command",
                },
                "commit_required": True,
                "dry_run": False,
                "warnings": [],
            }
        )

        self.assertEqual(
            message,
            "\n".join(
                [
                    "State updated: `blocked`",
                    "Reason: waiting on credentials",
                    "Stored: mapped project `LIFECYCLE_STATE.md`",
                    "Project commit required.",
                ]
            ),
        )

    def test_formats_registry_write_confirmation(self):
        message = format_state_write_confirmation(
            {
                "ok": True,
                "operation": "write-state",
                "source_type": "channel-local-registry",
                "before": None,
                "after": {
                    "state": "paused",
                    "reason": "until Friday",
                    "source": "discord-command",
                },
                "commit_required": False,
                "dry_run": False,
                "warnings": [],
            }
        )

        self.assertEqual(
            message,
            "\n".join(
                [
                    "State updated: `paused`",
                    "Reason: until Friday",
                    "Stored: channel-local registry",
                ]
            ),
        )

    def test_formats_unchanged_state_confirmation(self):
        message = format_state_write_confirmation(
            {
                "ok": True,
                "operation": "write-state",
                "source_type": "mapped-project",
                "before": {
                    "state": "active",
                    "reason": "current work",
                    "source": "discord-command",
                },
                "after": {
                    "state": "active",
                    "reason": "current work",
                    "source": "discord-command",
                },
                "commit_required": True,
                "dry_run": False,
                "warnings": ["existing registry entry ignored"],
            }
        )

        self.assertIn("State unchanged: `active`", message)
        self.assertIn("Warning: existing registry entry ignored", message)

    def test_rejects_failed_result(self):
        with self.assertRaises(LifecycleResponseError):
            format_state_write_confirmation(
                {
                    "ok": False,
                    "operation": "write-state",
                    "after": None,
                }
            )

    def test_rejects_status_result(self):
        with self.assertRaises(LifecycleResponseError):
            format_state_write_confirmation(
                {
                    "ok": True,
                    "operation": "read-status",
                    "after": None,
                }
            )

    def test_formats_mapped_project_status_response(self):
        message = format_state_status_response(
            {
                "ok": True,
                "operation": "read-status",
                "source_type": "mapped-project",
                "after": {
                    "state": "blocked",
                    "since": "2026-07-10",
                    "updated_at": "2026-07-10T12:00:00+00:00",
                    "reason": "waiting on credentials",
                    "source": "discord-command",
                },
                "warnings": [],
            }
        )

        self.assertEqual(
            message,
            "\n".join(
                [
                    "State: `blocked`",
                    "Reason: waiting on credentials",
                    "Since: 2026-07-10",
                    "Updated: 2026-07-10T12:00:00+00:00",
                    "Source: mapped project `LIFECYCLE_STATE.md`",
                ]
            ),
        )

    def test_formats_registry_status_response(self):
        message = format_state_status_response(
            {
                "ok": True,
                "operation": "read-status",
                "source_type": "channel-local-registry",
                "after": {
                    "state": "paused",
                    "reason": "until Friday",
                    "source": "discord-command",
                },
                "warnings": [],
            }
        )

        self.assertEqual(
            message,
            "\n".join(
                [
                    "State: `paused`",
                    "Reason: until Friday",
                    "Source: channel-local registry",
                ]
            ),
        )

    def test_formats_empty_status_response(self):
        message = format_state_status_response(
            {
                "ok": True,
                "operation": "read-status",
                "source_type": "channel-local-registry",
                "after": None,
                "warnings": [],
            }
        )

        self.assertEqual(
            message,
            "\n".join(
                [
                    "No lifecycle state recorded yet.",
                    "Checked: channel-local registry",
                ]
            ),
        )

    def test_formats_status_response_warnings(self):
        message = format_state_status_response(
            {
                "ok": True,
                "operation": "read-status",
                "source_type": "mapped-project",
                "after": {
                    "state": "active",
                    "reason": "current work",
                    "source": "discord-command",
                },
                "warnings": ["registry shadow ignored"],
            }
        )

        self.assertIn("Warning: registry shadow ignored", message)

    def test_rejects_write_result_for_status_response(self):
        with self.assertRaises(LifecycleResponseError):
            format_state_status_response(
                {
                    "ok": True,
                    "operation": "write-state",
                    "after": {
                        "state": "active",
                        "reason": "current work",
                        "source": "discord-command",
                    },
                }
            )

    def test_formats_invalid_state_error_with_allowed_states(self):
        try:
            parse_state_set_command("state waiting on vendor")
        except LifecycleCommandError as error:
            message = format_lifecycle_command_error(error)
        else:
            self.fail("Expected invalid lifecycle state")

        self.assertEqual(
            message,
            "\n".join(
                [
                    "Invalid lifecycle state 'waiting'.",
                    "Allowed states: `active`, `paused`, `blocked`, "
                    "`incident`, `pending-approval`, `ktlo`, `spike`, `archived`",
                ]
            ),
        )

    def test_formats_missing_state_error_with_allowed_states(self):
        message = format_lifecycle_command_error(
            LifecycleCommandError("Expected lifecycle state after `state`")
        )

        self.assertEqual(
            message,
            "\n".join(
                [
                    "Expected lifecycle state after `state`",
                    "Allowed states: `active`, `paused`, `blocked`, "
                    "`incident`, `pending-approval`, `ktlo`, `spike`, `archived`",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
