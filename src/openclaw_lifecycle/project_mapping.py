"""Workspace channel-map update helpers for `map project here`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .commands import MapProjectHereCommand
from .context import CurrentChannelContext
from .mapping import ProjectMappingError

_PROJECT_RE = re.compile(r"project folder(?:/repo root)? `([^`]+)`")
_REMOTE_RE = re.compile(r"GitHub remote `([^`]+)`")
_ARROW_RE = re.compile(r"^- (?P<labels>.+?) → `(?P<target_id>\d+)`(?: \((?P<notes>.*)\))?$")


class MapProjectHereError(ValueError):
    """Raised when `map project here` cannot safely update mapping state."""


@dataclass(frozen=True)
class MapProjectHereOptions:
    """Runtime options for mapping the current channel to a project."""

    workspace_root: str | Path
    map_path: str | Path
    index_path: str | Path
    registry_path: str | Path
    today: date
    dry_run: bool = False


def map_project_here(
    channel: CurrentChannelContext,
    command: MapProjectHereCommand,
    options: MapProjectHereOptions,
) -> dict[str, Any]:
    """Link the current Discord channel to an existing project folder."""

    workspace_root = Path(options.workspace_root).resolve()
    map_path = Path(options.map_path)
    index_path = Path(options.index_path)
    registry_path = Path(options.registry_path)
    project_folder = _normalize_project_folder(command.project)
    project_path = (workspace_root / project_folder).resolve()
    _verify_project_path(workspace_root, project_folder, project_path)
    git = _git_context(project_path)
    remote = _origin_remote(project_path)

    index = _read_index(index_path)
    entry, alternates = _entry_for_channel(index, channel.channel_id)
    if alternates:
        raise MapProjectHereError(
            f"Discord channel id {channel.channel_id!r} matched multiple map rows"
        )

    existing_folders = _string_list(entry.get("project_folders")) if entry else []
    if len(existing_folders) > 1:
        raise MapProjectHereError(
            f"Discord channel id {channel.channel_id!r} already has multiple projects"
        )
    if existing_folders and existing_folders[0] != project_folder:
        raise MapProjectHereError(
            "Current channel is already mapped to "
            f"{existing_folders[0]!r}, not {project_folder!r}"
        )

    before_line = str(entry.get("raw", "")) if entry else ""
    after_line = (
        before_line
        if existing_folders
        else _mapped_line(
            channel=channel,
            entry=entry,
            project_folder=project_folder,
            remote=remote,
            mapped_on=options.today,
        )
    )
    registry_entry = _registry_entry(registry_path, channel.channel_id)

    if not options.dry_run and after_line != before_line:
        _write_map_line(map_path, entry, after_line)
        _write_index(index_path, _build_index(map_path, workspace_root))

    return {
        "schema": "openclaw.lifecycle.map_project_here_result.v1",
        "ok": True,
        "operation": "map-project-here",
        "channel": _channel_packet(channel),
        "project": {
            "folder": project_folder,
            "path": str(project_path),
            "github_remote": remote,
        },
        "map": {
            "path": str(map_path),
            "index_path": str(index_path),
            "before_line": before_line,
            "after_line": after_line,
            "changed": after_line != before_line,
        },
        "registry": {
            "path": str(registry_path),
            "entry_key": channel.channel_id,
            "entry_exists": registry_entry is not None,
            "state": str(registry_entry.get("state", "")) if registry_entry else "",
        },
        "git": git,
        "commit_required": after_line != before_line and not options.dry_run,
        "dry_run": options.dry_run,
        "warnings": _warnings(registry_entry),
        "errors": [],
    }


def format_map_project_here_response(result: Mapping[str, Any]) -> str:
    """Format a concise Discord response for `map project here`."""

    project = _mapping(result.get("project"))
    map_info = _mapping(result.get("map"))
    registry = _mapping(result.get("registry"))
    lines = [
        f"Mapped this channel to `{project.get('folder', '')}`."
        if map_info.get("changed")
        else f"This channel is already mapped to `{project.get('folder', '')}`.",
        "Updated: Discord channel map and generated index"
        if map_info.get("changed")
        else "Updated: nothing needed",
    ]
    remote = project.get("github_remote")
    if remote:
        lines.append(f"Remote: `{remote}`")
    if registry.get("entry_exists"):
        state = registry.get("state") or "unknown"
        lines.append(
            "Note: channel-local registry state exists "
            f"(`{state}`); migration is still a separate backlog item."
        )
    if result.get("commit_required"):
        lines.append("Workspace map/index changes need committing in the workspace repo.")
    return "\n".join(lines)


def _normalize_project_folder(value: str) -> str:
    raw = value.strip().strip("`'\"")
    if not raw:
        raise MapProjectHereError("Project name is required")
    path = Path(raw)
    if path.is_absolute():
        raise MapProjectHereError(f"Project folder must be relative: {raw!r}")
    if path.parts and path.parts[0] != "projects":
        path = Path("projects") / path
    if any(part == ".." for part in path.parts):
        raise MapProjectHereError(f"Project folder must not traverse upward: {raw!r}")
    if len(path.parts) < 2 or path.parts[0] != "projects":
        raise MapProjectHereError(f"Project folder must be under projects/: {raw!r}")
    return path.as_posix()


def _verify_project_path(workspace_root: Path, project_folder: str, project_path: Path) -> None:
    expected = (workspace_root / project_folder).resolve()
    if project_path != expected:
        raise MapProjectHereError("Project path escaped workspace root")
    if not project_path.is_dir():
        raise MapProjectHereError(f"Project folder does not exist: {project_folder}")
    git = _git_context(project_path)
    if not git["is_git_repo"] or Path(str(git["top_level"])).resolve() != project_path:
        raise MapProjectHereError(f"Project folder is not its own git repo: {project_folder}")


def _git_context(project_path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=project_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "is_git_repo": result.returncode == 0,
        "top_level": result.stdout.strip(),
        "error": result.stderr.strip(),
    }


def _origin_remote(project_path: Path) -> str:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=project_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return _display_remote(result.stdout.strip())


def _display_remote(value: str) -> str:
    if value.startswith("https://github.com/"):
        return value.removeprefix("https://github.com/").removesuffix(".git")
    match = re.match(r"git@github\.com:(?P<repo>.+?)(?:\.git)?$", value)
    if match:
        return match.group("repo")
    return value


def _read_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"entries": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MapProjectHereError("Discord channel index must be a JSON object")
    return data


def _entry_for_channel(
    index: Mapping[str, Any],
    channel_id: str,
) -> tuple[Mapping[str, Any] | None, list[Mapping[str, Any]]]:
    entries = index.get("entries", [])
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise MapProjectHereError("Discord channel index entries must be a list")
    matches = [
        entry
        for entry in entries
        if isinstance(entry, Mapping)
        and entry.get("kind") != "guild"
        and str(entry.get("target_id", "")).strip() == channel_id
    ]
    if not matches:
        return None, []
    return matches[0], matches[1:]


def _mapped_line(
    *,
    channel: CurrentChannelContext,
    entry: Mapping[str, Any] | None,
    project_folder: str,
    remote: str,
    mapped_on: date,
) -> str:
    metadata = [f"project folder `{project_folder}`"]
    if remote:
        metadata.append(f"GitHub remote `{remote}`")
    metadata.append(f"mapped to existing project on {mapped_on.isoformat()}")
    addition = "; ".join(metadata)

    if entry:
        raw = str(entry.get("raw", ""))
        match = _ARROW_RE.match(raw)
        if not match:
            raise MapProjectHereError("Existing map row has unsupported format")
        notes = match.group("notes")
        if notes:
            return raw[:-1] + f"; {addition})"
        return f"{raw} ({addition})"

    label = channel.channel_name.strip().lstrip("#") or Path(project_folder).name
    return f"- `#{label}` → `{channel.channel_id}` ({addition})"


def _write_map_line(
    path: Path,
    entry: Mapping[str, Any] | None,
    line: str,
) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if entry is None:
        lines.append(line)
    else:
        line_number = int(entry.get("line", 0))
        if line_number < 1 or line_number > len(lines):
            raise MapProjectHereError("Existing map row line number is invalid")
        lines[line_number - 1] = line
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_index(map_path: Path, workspace_root: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(map_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.startswith("- "):
            continue
        entry: dict[str, Any] = {
            "line": line_number,
            "raw": raw_line,
            "labels": re.findall(r"`([^`]+)`", raw_line),
            "notes": "",
            "project_folders": _PROJECT_RE.findall(raw_line),
            "github_remotes": _REMOTE_RE.findall(raw_line),
            "cron_job_ids": re.findall(r"cron job `([^`]+)`", raw_line),
            "export_paths": [],
            "original_channel_ids": re.findall(r"original channel `(\d+)`", raw_line),
            "source_ids": re.findall(r"source (?:category|channel) `(\d+)`", raw_line),
        }
        guild_match = re.match(
            r"^- Guild `(?P<guild_id>\d+)` → `(?P<guild_name>[^`]+)`(?: \((?P<notes>.*)\))?$",
            raw_line,
        )
        mapping_match = _ARROW_RE.match(raw_line)
        if guild_match:
            entry.update(
                {
                    "kind": "guild",
                    "guild_id": guild_match.group("guild_id"),
                    "guild_name": guild_match.group("guild_name"),
                    "labels": [guild_match.group("guild_name")],
                    "notes": guild_match.group("notes") or "",
                }
            )
        elif mapping_match:
            entry.update(
                {
                    "kind": "mapping",
                    "target_id": mapping_match.group("target_id"),
                    "labels": re.findall(r"`([^`]+)`", mapping_match.group("labels")),
                    "notes": mapping_match.group("notes") or "",
                }
            )
        else:
            entry["kind"] = "note"
            entry["notes"] = raw_line[2:]
        entries.append(entry)
    return {
        "schema": "openclaw.discord_channel_index.v1",
        "source": str(map_path.resolve().relative_to(workspace_root)),
        "entry_count": len(entries),
        "entries": entries,
    }


def _write_index(path: Path, index: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _registry_entry(path: Path, channel_id: str) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    channels = data.get("channels", {}) if isinstance(data, Mapping) else {}
    entry = channels.get(channel_id) if isinstance(channels, Mapping) else None
    return entry if isinstance(entry, Mapping) else None


def _warnings(registry_entry: Mapping[str, Any] | None) -> list[str]:
    if registry_entry:
        return ["channel-local registry state exists; migration is not part of this command"]
    return []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProjectMappingError("Expected a list of strings")
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _channel_packet(channel: CurrentChannelContext) -> dict[str, str]:
    packet = {"channel_id": channel.channel_id}
    if channel.channel_name:
        packet["channel_name"] = channel.channel_name
    if channel.guild_id:
        packet["guild_id"] = channel.guild_id
    return packet
