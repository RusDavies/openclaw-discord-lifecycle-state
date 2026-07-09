import unittest

from openclaw_lifecycle import LifecycleCommandError, StateSetCommand
from openclaw_lifecycle.commands import parse_state_set_command


class StateSetCommandParsingTests(unittest.TestCase):
    def test_parse_minimal_state_command(self):
        self.assertEqual(
            parse_state_set_command("state active"),
            StateSetCommand(state="active", reason=""),
        )

    def test_parse_state_command_with_reason(self):
        self.assertEqual(
            parse_state_set_command("state blocked waiting on credentials"),
            StateSetCommand(state="blocked", reason="waiting on credentials"),
        )

    def test_parse_collapses_reason_whitespace(self):
        self.assertEqual(
            parse_state_set_command("state paused  until\n\nFriday"),
            StateSetCommand(state="paused", reason="until Friday"),
        )

    def test_parse_accepts_newline_between_state_and_reason(self):
        self.assertEqual(
            parse_state_set_command("state paused\nuntil Friday"),
            StateSetCommand(state="paused", reason="until Friday"),
        )

    def test_parse_tolerates_case_and_accidental_separator(self):
        self.assertEqual(
            parse_state_set_command("  State: BLOCKED - Waiting on Bob  "),
            StateSetCommand(state="blocked", reason="Waiting on Bob"),
        )

    def test_parse_tolerates_markdown_wrapped_state(self):
        self.assertEqual(
            parse_state_set_command("state `pending-approval`: needs Example User"),
            StateSetCommand(state="pending-approval", reason="needs Example User"),
        )

    def test_parse_tolerates_state_reason_without_space_after_colon(self):
        self.assertEqual(
            parse_state_set_command("state blocked:waiting"),
            StateSetCommand(state="blocked", reason="waiting"),
        )

    def test_parse_rejects_missing_state(self):
        with self.assertRaises(LifecycleCommandError):
            parse_state_set_command("state")

    def test_parse_rejects_wrong_command(self):
        with self.assertRaises(LifecycleCommandError):
            parse_state_set_command("status blocked")

    def test_parse_rejects_invalid_state_with_allowed_values(self):
        with self.assertRaises(LifecycleCommandError) as context:
            parse_state_set_command("state waiting on credentials")

        message = str(context.exception)
        self.assertIn("Invalid lifecycle state", message)
        self.assertIn("active", message)
        self.assertIn("archived", message)

    def test_parse_rejects_non_string_command(self):
        with self.assertRaises(LifecycleCommandError):
            parse_state_set_command(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
