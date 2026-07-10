"""Runtime adapter packet validation for Discord channel lookup results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import CurrentChannelContext
from .mapping import ProjectMappingError, SafeProjectMapping


class ChannelLookupPacketError(ValueError):
    """Raised when a normalized channel lookup packet is invalid."""


@dataclass(frozen=True)
class ChannelLookupResolution:
    """Validated mapping decision from a normalized runtime lookup packet."""

    status: str
    mapping: SafeProjectMapping | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def resolve_channel_lookup_packet(
    channel: CurrentChannelContext,
    packet: Mapping[str, Any],
    workspace_root: str | Path | None = None,
) -> ChannelLookupResolution:
    """Validate a normalized runtime adapter packet.

    The runtime adapter is responsible for calling OpenClaw `channel_lookup`.
    This helper consumes the already-normalized packet shape documented in
    `docs/channel-lookup-adapter-boundary.md` and converts safe mapped packets
    into `SafeProjectMapping`.
    """

    status = _required_text(packet, "status")
    if status not in {"mapped", "unmapped", "ambiguous", "error"}:
        raise ChannelLookupPacketError(f"Unsupported lookup packet status: {status!r}")

    if _optional_text(packet, "channel_id") not in {"", channel.channel_id}:
        raise ChannelLookupPacketError(
            f"Lookup packet channel id does not match current channel {channel.channel_id!r}"
        )

    errors = tuple(_string_list(packet.get("errors"), field="errors"))
    warnings = tuple(_string_list(packet.get("warnings"), field="warnings"))

    if status == "mapped":
        mapping_packet = packet.get("mapping")
        if not isinstance(mapping_packet, Mapping):
            raise ChannelLookupPacketError("Mapped lookup packet requires a mapping object")
        return ChannelLookupResolution(
            status="mapped",
            mapping=_safe_mapping_from_packet(channel, mapping_packet, workspace_root),
            errors=errors,
            warnings=warnings,
        )

    if packet.get("mapping") is not None:
        raise ChannelLookupPacketError(
            f"Lookup packet status {status!r} must not include a mapping object"
        )

    return ChannelLookupResolution(
        status=status,
        mapping=None,
        errors=errors,
        warnings=warnings,
    )


def _safe_mapping_from_packet(
    channel: CurrentChannelContext,
    mapping_packet: Mapping[str, Any],
    workspace_root: str | Path | None,
) -> SafeProjectMapping:
    channel_id = _required_text(mapping_packet, "channel_id")
    if channel_id != channel.channel_id:
        raise ChannelLookupPacketError(
            f"Mapping channel id does not match current channel {channel.channel_id!r}"
        )

    project_folder = _validate_project_folder(
        _required_text(mapping_packet, "project_folder")
    )
    return SafeProjectMapping(
        channel_id=channel_id,
        project_folder=project_folder,
        project_path=_project_path(project_folder, workspace_root),
        channel_name=(
            channel.channel_name
            or _optional_text(mapping_packet, "channel_name").lstrip("#")
        ),
        github_remotes=tuple(
            _string_list(mapping_packet.get("github_remotes"), field="github_remotes")
        ),
    )


def _required_text(mapping: Mapping[str, Any], key: str) -> str:
    value = _optional_text(mapping, key)
    if not value:
        raise ChannelLookupPacketError(f"Lookup packet missing required field {key!r}")
    return value


def _optional_text(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ChannelLookupPacketError(f"Lookup packet field {key!r} must be a string")
    return value.strip()


def _string_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ChannelLookupPacketError(f"Lookup packet field {field!r} must be a list")

    values = []
    for item in value:
        if not isinstance(item, str):
            raise ChannelLookupPacketError(
                f"Lookup packet field {field!r} must contain only strings"
            )
        if item.strip():
            values.append(item.strip())
    return values


def _validate_project_folder(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        raise ProjectMappingError(f"Project folder must be relative: {value!r}")
    if any(part == ".." for part in path.parts):
        raise ProjectMappingError(f"Project folder must not traverse upward: {value!r}")
    if not path.parts or path.parts[0] != "projects":
        raise ProjectMappingError(f"Project folder must be under projects/: {value!r}")
    if len(path.parts) < 2:
        raise ProjectMappingError(f"Project folder must include a project name: {value!r}")
    return path.as_posix()


def _project_path(project_folder: str, workspace_root: str | Path | None) -> str:
    if workspace_root is None:
        return project_folder
    return str((Path(workspace_root) / project_folder).resolve())
