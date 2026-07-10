"""Discord runtime adapter for lifecycle state commands."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from .commands import LifecycleCommandError
from .context import CurrentChannelContext, resolve_current_channel_context
from .discord_response import (
    format_lifecycle_command_error,
    format_state_status_response,
    format_state_write_confirmation,
)
from .workflow import LifecycleWorkflowOptions, handle_lifecycle_command

_SCHEMA = "openclaw.lifecycle.discord_runtime_result.v1"
_LOOKUP_PACKET_SCHEMA = "openclaw.lifecycle.channel_lookup_adapter.v1"
_PROJECT_FOLDER_RE = re.compile(r"project folder `(?P<value>projects/[^`]+)`")
_GITHUB_REMOTE_RE = re.compile(r"GitHub remote `(?P<value>[^`]+)`")


class DiscordRuntimeAdapterError(ValueError):
    """Raised when the Discord runtime adapter cannot normalize runtime data."""


@dataclass(frozen=True)
class DiscordRuntimeOptions:
    """Runtime options for a Discord lifecycle command."""

    actor: str
    now: datetime
    registry_path: str | Path
    workspace_root: str | Path | None = None


def handle_discord_state_command(
    raw_command: str,
    conversation_info: Mapping[str, Any],
    channel_metadata: Mapping[str, Any] | None,
    channel_lookup: Callable[[str], Mapping[str, Any]],
    send_message: Callable[[str], Any],
    options: DiscordRuntimeOptions,
) -> dict[str, Any]:
    """Run a Discord `state` command and send the visible response.

    The callables keep OpenClaw tool details outside the package. Runtime code
    should pass `channel_lookup(channel_id)` and a channel-local send function.
    """

    channel = resolve_current_channel_context(conversation_info, channel_metadata)
    lookup_packet: dict[str, Any] | None = None
    try:
        lookup_packet = normalize_channel_lookup_response(
            channel,
            channel_lookup(channel.channel_id),
        )
        result = handle_lifecycle_command(
            raw_command,
            channel,
            lookup_packet,
            LifecycleWorkflowOptions(
                actor=options.actor,
                now=options.now,
                registry_path=options.registry_path,
                workspace_root=options.workspace_root,
            ),
        )
        message = _format_success(result)
        send_receipt = send_message(message)
        return {
            "schema": _SCHEMA,
            "ok": True,
            "channel": _channel_packet(channel),
            "lookup_packet": lookup_packet,
            "message": message,
            "send_receipt": send_receipt,
            "result": result,
            "error": "",
        }
    except Exception as error:
        message = _format_error(error)
        send_receipt = send_message(message)
        return {
            "schema": _SCHEMA,
            "ok": False,
            "channel": _channel_packet(channel),
            "lookup_packet": lookup_packet,
            "message": message,
            "send_receipt": send_receipt,
            "result": None,
            "error": str(error),
        }


def normalize_channel_lookup_response(
    channel: CurrentChannelContext,
    response: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize OpenClaw `channel_lookup` output for lifecycle workflow code."""

    matches = _matches(response)
    if not matches:
        return _lookup_packet("unmapped", channel)
    if len(matches) > 1:
        return _lookup_packet(
            "ambiguous",
            channel,
            errors=["channel_lookup returned multiple matches"],
        )

    match = matches[0]
    match_channel_id = _optional_text(match.get("channelId")) or channel.channel_id
    if match_channel_id != channel.channel_id:
        return _lookup_packet(
            "error",
            channel,
            errors=[
                "channel_lookup returned a channel id that does not match the current channel"
            ],
        )

    project_folder = _project_folder(match)
    if not project_folder:
        return _lookup_packet("unmapped", channel)

    mapping = {
        "channel_id": channel.channel_id,
        "channel_name": channel.channel_name or _first_name(match),
        "project_folder": project_folder,
        "github_remotes": _github_remotes(match),
    }
    return _lookup_packet("mapped", channel, mapping=mapping)


def _format_success(result: Mapping[str, Any]) -> str:
    operation = result.get("operation")
    if operation == "write-state":
        return format_state_write_confirmation(result)
    if operation == "read-status":
        return format_state_status_response(result)
    raise DiscordRuntimeAdapterError(f"Unsupported lifecycle operation: {operation!r}")


def _format_error(error: Exception) -> str:
    if isinstance(error, LifecycleCommandError):
        return format_lifecycle_command_error(error)
    return str(error).strip() or "Lifecycle command failed."


def _lookup_packet(
    status: str,
    channel: CurrentChannelContext,
    *,
    mapping: Mapping[str, Any] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "schema": _LOOKUP_PACKET_SCHEMA,
        "status": status,
        "channel_id": channel.channel_id,
    }
    if mapping is not None:
        packet["mapping"] = dict(mapping)
    if errors:
        packet["errors"] = errors
    if warnings:
        packet["warnings"] = warnings
    return packet


def _matches(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    matches = response.get("matches")
    if matches is None:
        return []
    if not isinstance(matches, Sequence) or isinstance(matches, (str, bytes)):
        raise DiscordRuntimeAdapterError("channel_lookup matches must be a list")
    return [item for item in matches if isinstance(item, Mapping)]


def _project_folder(match: Mapping[str, Any]) -> str:
    text = "\n".join(
        value
        for value in (
            _optional_text(match.get("notes")),
            _optional_text(match.get("raw")),
        )
        if value
    )
    found = _PROJECT_FOLDER_RE.search(text)
    return found.group("value") if found else ""


def _github_remotes(match: Mapping[str, Any]) -> list[str]:
    text = "\n".join(
        value
        for value in (
            _optional_text(match.get("notes")),
            _optional_text(match.get("raw")),
        )
        if value
    )
    remotes: list[str] = []
    for found in _GITHUB_REMOTE_RE.finditer(text):
        remote = found.group("value")
        if remote not in remotes:
            remotes.append(remote)
    return remotes


def _first_name(match: Mapping[str, Any]) -> str:
    names = match.get("names")
    if not isinstance(names, Sequence) or isinstance(names, (str, bytes)):
        return ""
    for name in names:
        if isinstance(name, str) and name.strip():
            return name.strip().lstrip("#")
    return ""


def _optional_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _channel_packet(channel: CurrentChannelContext) -> dict[str, str]:
    packet = {"channel_id": channel.channel_id}
    for key in (
        "channel_name",
        "guild_id",
        "guild_name",
        "category_id",
        "category_name",
    ):
        value = getattr(channel, key)
        if value:
            packet[key] = value
    return packet
