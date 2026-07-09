"""Lifecycle Discord command parsing."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .state import LifecycleStateError, validate_state

_STATE_SET_PATTERN = re.compile(
    r"""
    \A
    \s*
    state
    \b
    \s*
    (?:
        [:=-]
        \s*
    )?
    (?P<body>.*?)
    \s*
    \Z
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


class LifecycleCommandError(ValueError):
    """Raised when a lifecycle command cannot be parsed."""


@dataclass(frozen=True)
class StateSetCommand:
    """Parsed `state <value> [reason]` command."""

    state: str
    reason: str


def parse_state_set_command(value: str) -> StateSetCommand:
    """Parse a `state <value> [reason]` command.

    The command word and accidental separators are forgiving because Discord
    command text is hand-written. The stored state is still normalized through
    lifecycle-state validation.
    """

    if not isinstance(value, str):
        raise LifecycleCommandError("Lifecycle command must be a string")

    match = _STATE_SET_PATTERN.match(value.replace("\r\n", "\n").replace("\r", "\n"))
    if not match:
        raise LifecycleCommandError("Expected `state <value> [reason]`")

    body = match.group("body").strip()
    if not body:
        raise LifecycleCommandError("Expected lifecycle state after `state`")

    raw_state, raw_reason = _split_state_and_reason(body)
    normalized_state = _normalize_state_token(raw_state)

    try:
        state = validate_state(normalized_state)
    except LifecycleStateError as error:
        raise LifecycleCommandError(str(error)) from error

    return StateSetCommand(state=state, reason=_normalize_reason(raw_reason))


def _split_state_and_reason(body: str) -> tuple[str, str]:
    pieces = re.split(r"\s+", body, maxsplit=1)
    if len(pieces) == 2:
        return pieces[0], pieces[1]

    for delimiter in (":", ",", ";"):
        if delimiter in body:
            possible_state, possible_reason = body.split(delimiter, 1)
            if possible_state:
                return possible_state, possible_reason

    return body, ""


def _normalize_state_token(value: str) -> str:
    return value.strip().rstrip(":,;").strip("`'\"").lower()


def _normalize_reason(value: str) -> str:
    reason = value.strip()
    if reason.startswith(("-", ":", ",", ";")):
        reason = reason[1:].strip()
    return " ".join(reason.split())
