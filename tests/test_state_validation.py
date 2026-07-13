import unittest

from openclaw_lifecycle import (
    ALLOWED_STATES,
    LifecycleStateError,
    allowed_states_text,
    is_valid_state,
    validate_state,
)


class LifecycleStateValidationTests(unittest.TestCase):
    def test_all_allowed_states_validate(self):
        for state in ALLOWED_STATES:
            with self.subTest(state=state):
                self.assertEqual(validate_state(state), state)

    def test_validation_trims_outer_whitespace(self):
        self.assertEqual(validate_state(" blocked "), "blocked")

    def test_invalid_state_raises_with_allowed_values(self):
        with self.assertRaises(LifecycleStateError) as context:
            validate_state("waiting")

        message = str(context.exception)
        self.assertIn("Invalid lifecycle state", message)
        self.assertIn("active", message)
        self.assertIn("archived", message)

    def test_non_string_state_raises(self):
        with self.assertRaises(LifecycleStateError):
            validate_state(None)  # type: ignore[arg-type]

    def test_is_valid_state(self):
        self.assertTrue(is_valid_state("active"))
        self.assertTrue(is_valid_state(" active "))
        self.assertFalse(is_valid_state("Active"))
        self.assertFalse(is_valid_state("waiting"))
        self.assertFalse(is_valid_state(None))

    def test_allowed_states_text_is_stable(self):
        self.assertEqual(
            allowed_states_text(),
            "active, paused, blocked, incident, pending-approval, ktlo, spike, archived",
        )


if __name__ == "__main__":
    unittest.main()
