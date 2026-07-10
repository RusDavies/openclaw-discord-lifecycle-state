"""Safe Discord channel to project mapping resolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import CurrentChannelContext


class ProjectMappingError(ValueError):
    """Raised when project mapping data cannot be used safely."""


@dataclass(frozen=True)
class SafeProjectMapping:
    """Safely resolved project mapping for the current Discord channel."""

    channel_id: str
    project_folder: str
    project_path: str
    channel_name: str = ""
    github_remotes: tuple[str, ...] = ()


def resolve_safe_project_mapping(
    channel: CurrentChannelContext,
    channel_index: Mapping[str, Any],
    workspace_root: str | Path | None = None,
) -> SafeProjectMapping | None:
    """Resolve a safe project mapping by exact Discord channel id.

    Returns `None` when the current channel is known but unmapped. Raises when
    the mapping is ambiguous or points outside the expected project folder
    namespace.
    """

    matches = _exact_channel_matches(channel.channel_id, channel_index)
    if not matches:
        return None
    if len(matches) > 1:
        raise ProjectMappingError(
            f"Ambiguous mapping for Discord channel id {channel.channel_id!r}"
        )

    entry = matches[0]
    project_folders = _string_list(entry.get("project_folders"))
    if not project_folders:
        return None
    if len(project_folders) > 1:
        raise ProjectMappingError(
            f"Multiple project folders for Discord channel id {channel.channel_id!r}"
        )

    project_folder = _validate_project_folder(project_folders[0])
    return SafeProjectMapping(
        channel_id=channel.channel_id,
        project_folder=project_folder,
        project_path=_project_path(project_folder, workspace_root),
        channel_name=channel.channel_name or _first_label(entry),
        github_remotes=tuple(_string_list(entry.get("github_remotes"))),
    )


def _exact_channel_matches(
    channel_id: str,
    channel_index: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    entries = channel_index.get("entries")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise ProjectMappingError("Channel index must contain an entries list")

    matches: list[Mapping[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("kind") == "guild":
            continue
        if str(entry.get("target_id", "")).strip() == channel_id:
            matches.append(entry)
    return matches


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProjectMappingError("Expected a list of strings in channel index")

    values = []
    for item in value:
        if isinstance(item, str) and item.strip():
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


def _first_label(entry: Mapping[str, Any]) -> str:
    labels = _string_list(entry.get("labels"))
    return labels[0].lstrip("#") if labels else ""
