"""Discord-facing lifecycle response text."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .state import ALLOWED_STATES


class LifecycleResponseError(ValueError):
    """Raised when a lifecycle result packet cannot be formatted."""


def format_lifecycle_command_error(error: Exception) -> str:
    """Format a concise visible response for lifecycle command errors."""

    message = str(error).strip() or "Lifecycle command failed."
    invalid_state = _invalid_state_from_message(message)
    if invalid_state:
        lines = [f"Invalid lifecycle state {invalid_state}."]
    else:
        lines = [message]

    lines.append(f"Allowed states: {_allowed_states_markdown()}")
    return "\n".join(lines)


def format_state_write_confirmation(result: Mapping[str, Any]) -> str:
    """Format a concise visible confirmation for a successful state write."""

    if result.get("operation") != "write-state":
        raise LifecycleResponseError("Expected a write-state result packet")
    if result.get("ok") is not True:
        raise LifecycleResponseError("Cannot format a successful confirmation for a failed result")

    after = result.get("after")
    if not isinstance(after, Mapping):
        raise LifecycleResponseError("Write result packet is missing an after snapshot")

    state = _required_text(after, "state")
    reason = _optional_text(after, "reason")
    before = result.get("before")
    previous_state = ""
    if isinstance(before, Mapping):
        previous_state = _optional_text(before, "state")

    verb = "unchanged" if previous_state == state else "updated"
    if result.get("dry_run") is True:
        verb = "would be"

    lines = [f"State {verb}: `{state}`"]
    if reason:
        lines.append(f"Reason: {reason}")

    storage = _storage_text(result)
    if storage:
        lines.append(f"Stored: {storage}")

    if result.get("commit_required") is True:
        lines.append("Project commit required.")

    for warning in _string_list(result.get("warnings")):
        lines.append(f"Warning: {warning}")

    return "\n".join(lines)


def format_state_status_response(result: Mapping[str, Any]) -> str:
    """Format a concise visible response for a lifecycle status read."""

    if result.get("operation") != "read-status":
        raise LifecycleResponseError("Expected a read-status result packet")
    if result.get("ok") is not True:
        raise LifecycleResponseError("Cannot format a successful status response for a failed result")

    storage = _storage_text(result)
    after = result.get("after")
    if after is None:
        lines = ["No lifecycle state recorded yet."]
        if storage:
            lines.append(f"Checked: {storage}")
        return _append_warnings(lines, result)

    if not isinstance(after, Mapping):
        raise LifecycleResponseError("Status result packet after field must be an object or null")

    state = _required_text(after, "state")
    lines = [f"State: `{state}`"]

    reason = _optional_text(after, "reason")
    if reason:
        lines.append(f"Reason: {reason}")

    since = _optional_text(after, "since")
    if since:
        lines.append(f"Since: {since}")

    updated_at = _optional_text(after, "updated_at")
    if updated_at:
        lines.append(f"Updated: {updated_at}")

    if storage:
        lines.append(f"Source: {storage}")

    return _append_warnings(lines, result)


def _storage_text(result: Mapping[str, Any]) -> str:
    source_type = result.get("source_type")
    if source_type == "mapped-project":
        return "mapped project `LIFECYCLE_STATE.md`"
    if source_type == "channel-local-registry":
        return "channel-local registry"
    return ""


def _invalid_state_from_message(message: str) -> str:
    match = re.search(r"Invalid lifecycle state (?P<state>.+?);", message)
    return match.group("state") if match else ""


def _allowed_states_markdown() -> str:
    return ", ".join(f"`{state}`" for state in ALLOWED_STATES)


def _append_warnings(lines: list[str], result: Mapping[str, Any]) -> str:
    for warning in _string_list(result.get("warnings")):
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


def _required_text(mapping: Mapping[str, Any], key: str) -> str:
    value = _optional_text(mapping, key)
    if not value:
        raise LifecycleResponseError(f"Result packet missing required field {key!r}")
    return value


def _optional_text(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LifecycleResponseError(f"Result packet field {key!r} must be a string")
    return value.strip()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise LifecycleResponseError("Result packet warnings must be a list")
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
