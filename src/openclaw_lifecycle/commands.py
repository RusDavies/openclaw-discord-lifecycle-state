"""Lifecycle Discord command parsing."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .state import LifecycleStateError, validate_state

_STATE_COMMAND_PATTERN = re.compile(
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


@dataclass(frozen=True)
class StateStatusCommand:
    """Parsed `state` / `state status` command."""


@dataclass(frozen=True)
class MapProjectHereCommand:
    """Parsed `map project here <project>` command."""

    project: str


LifecycleCommand = StateSetCommand | StateStatusCommand
ProjectMappingCommand = MapProjectHereCommand

_MAP_PROJECT_HERE_PATTERN = re.compile(
    r"""
    \A
    \s*
    map
    \s+
    project
    \s+
    here
    \s+
    (?P<project>.+?)
    \s*
    \Z
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


def parse_lifecycle_command(value: str) -> LifecycleCommand:
    """Parse a lifecycle `state` command into a status read or state write."""

    if _is_status_body(_extract_state_command_body(value)):
        return StateStatusCommand()

    return parse_state_set_command(value)


def parse_state_status_command(value: str) -> StateStatusCommand:
    """Parse a `state` / `state status` command."""

    body = _extract_state_command_body(value)
    if not _is_status_body(body):
        raise LifecycleCommandError("Expected `state` or `state status`")

    return StateStatusCommand()


def parse_state_set_command(value: str) -> StateSetCommand:
    """Parse a `state <value> [reason]` command.

    The command word and accidental separators are forgiving because Discord
    command text is hand-written. The stored state is still normalized through
    lifecycle-state validation.
    """

    body = _extract_state_command_body(value)
    if not body:
        raise LifecycleCommandError("Expected lifecycle state after `state`")

    raw_state, raw_reason = _split_state_and_reason(body)
    normalized_state = _normalize_state_token(raw_state)

    try:
        state = validate_state(normalized_state)
    except LifecycleStateError as error:
        raise LifecycleCommandError(str(error)) from error

    return StateSetCommand(state=state, reason=_normalize_reason(raw_reason))


def parse_map_project_here_command(value: str) -> MapProjectHereCommand:
    """Parse `map project here <project>` into a mapping command."""

    if not isinstance(value, str):
        raise LifecycleCommandError("Lifecycle command must be a string")

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    match = _MAP_PROJECT_HERE_PATTERN.match(normalized)
    if not match:
        raise LifecycleCommandError("Expected `map project here <project>`")

    project = " ".join(match.group("project").strip().strip("`'\"").split())
    if not project:
        raise LifecycleCommandError("Expected project after `map project here`")
    return MapProjectHereCommand(project=project)


def _extract_state_command_body(value: str) -> str:
    if not isinstance(value, str):
        raise LifecycleCommandError("Lifecycle command must be a string")

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    match = _STATE_COMMAND_PATTERN.match(normalized)
    if not match:
        raise LifecycleCommandError("Expected lifecycle command beginning with `state`")

    return match.group("body").strip()


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


def _is_status_body(value: str) -> bool:
    normalized = (
        " ".join(value.split()).strip().rstrip(":,;.?!").strip("`'\"").lower()
    )
    return normalized in ("", "status")
