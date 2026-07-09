"""Lifecycle state validation."""

from __future__ import annotations

ALLOWED_STATES: tuple[str, ...] = (
    "active",
    "paused",
    "blocked",
    "pending-approval",
    "ktlo",
    "spike",
    "archived",
)

_ALLOWED_STATE_SET = frozenset(ALLOWED_STATES)


class LifecycleStateError(ValueError):
    """Raised when a lifecycle state value is invalid."""


def allowed_states_text() -> str:
    """Return allowed state values as a concise display string."""

    return ", ".join(ALLOWED_STATES)


def validate_state(value: str) -> str:
    """Validate and return a lifecycle state value.

    State values are intentionally exact lowercase command values. Alias support
    belongs in command parsing, not in the stored lifecycle state.
    """

    if not isinstance(value, str):
        raise LifecycleStateError(
            f"Lifecycle state must be a string; allowed values: {allowed_states_text()}"
        )

    state = value.strip()
    if state in _ALLOWED_STATE_SET:
        return state

    raise LifecycleStateError(
        f"Invalid lifecycle state {value!r}; allowed values: {allowed_states_text()}"
    )


def is_valid_state(value: object) -> bool:
    """Return whether a value is a valid lifecycle state."""

    return isinstance(value, str) and value.strip() in _ALLOWED_STATE_SET
