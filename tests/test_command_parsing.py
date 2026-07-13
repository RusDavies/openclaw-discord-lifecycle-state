import unittest

from openclaw_lifecycle import (
    LifecycleCommandError,
    StateSetCommand,
    StateStatusCommand,
)
from openclaw_lifecycle.commands import (
    parse_lifecycle_command,
    parse_state_set_command,
    parse_state_status_command,
)


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

    def test_parse_incident_state_command(self):
        self.assertEqual(
            parse_state_set_command("state incident database outage"),
            StateSetCommand(state="incident", reason="database outage"),
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


class StateStatusCommandParsingTests(unittest.TestCase):
    def test_parse_bare_state_as_status_command(self):
        self.assertEqual(parse_state_status_command("state"), StateStatusCommand())

    def test_parse_state_status_command(self):
        self.assertEqual(
            parse_state_status_command("state status"),
            StateStatusCommand(),
        )

    def test_parse_status_command_tolerates_case_and_separator(self):
        self.assertEqual(
            parse_state_status_command("  State: STATUS?  "),
            StateStatusCommand(),
        )

    def test_parse_status_command_tolerates_newline_between_words(self):
        self.assertEqual(
            parse_state_status_command("state\nstatus"),
            StateStatusCommand(),
        )

    def test_parse_status_command_tolerates_markdown_wrapped_status(self):
        self.assertEqual(
            parse_state_status_command("state `status`;"),
            StateStatusCommand(),
        )

    def test_parse_status_rejects_state_write_command(self):
        with self.assertRaises(LifecycleCommandError):
            parse_state_status_command("state active")

    def test_parse_status_rejects_wrong_command(self):
        with self.assertRaises(LifecycleCommandError):
            parse_state_status_command("status")


class LifecycleCommandParsingTests(unittest.TestCase):
    def test_dispatcher_parses_status_command(self):
        self.assertEqual(parse_lifecycle_command("state"), StateStatusCommand())

    def test_dispatcher_parses_explicit_status_command(self):
        self.assertEqual(
            parse_lifecycle_command("state status"),
            StateStatusCommand(),
        )

    def test_dispatcher_parses_state_set_command(self):
        self.assertEqual(
            parse_lifecycle_command("state blocked waiting"),
            StateSetCommand(state="blocked", reason="waiting"),
        )


if __name__ == "__main__":
    unittest.main()
