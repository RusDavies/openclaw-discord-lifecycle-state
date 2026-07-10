import unittest

from openclaw_lifecycle import (
    LifecycleResponseError,
    format_state_write_confirmation,
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


if __name__ == "__main__":
    unittest.main()
