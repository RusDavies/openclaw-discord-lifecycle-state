"""Mapped project lifecycle state file writes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import subprocess
from typing import Any

from .commands import StateSetCommand, StateStatusCommand
from .context import CurrentChannelContext
from .mapping import SafeProjectMapping
from .state import validate_state

_SCHEMA = "openclaw.lifecycle.command_result.v1"
_TITLE = "# Lifecycle State"
_REQUIRED_WRITE_KEYS = (
    "state",
    "since",
    "channel_id",
    "updated_by",
    "reason",
    "source",
    "updated_at",
)


class MappedProjectStateError(ValueError):
    """Raised when mapped project lifecycle state cannot be written safely."""


@dataclass(frozen=True)
class MappedProjectWriteOptions:
    """Metadata for a mapped project lifecycle state write."""

    actor: str
    now: datetime
    raw_command: str = ""
    source: str = "discord-command"
    dry_run: bool = False


def write_mapped_project_lifecycle_state(
    channel: CurrentChannelContext,
    mapping: SafeProjectMapping,
    command: StateSetCommand,
    options: MappedProjectWriteOptions,
) -> dict[str, Any]:
    """Write `LIFECYCLE_STATE.md` for a safely mapped project channel."""

    if mapping.channel_id != channel.channel_id:
        raise MappedProjectStateError(
            f"Mapping channel id does not match current channel {channel.channel_id!r}"
        )

    state = validate_state(command.state)
    project_path = Path(mapping.project_path).resolve()
    state_file = project_path / "LIFECYCLE_STATE.md"

    verification = [_verification("mapped_project_exists", project_path.is_dir())]
    if not project_path.is_dir():
        raise MappedProjectStateError(f"Mapped project folder does not exist: {project_path}")

    git_top_level = _git_top_level(project_path)
    git_boundary_ok = git_top_level == project_path
    verification.append(_verification("git_top_level_is_project", git_boundary_ok))
    if not git_boundary_ok:
        raise MappedProjectStateError(
            f"Mapped project git top-level is {git_top_level}, expected {project_path}"
        )

    before_fields = _read_state_file(state_file)
    before = _snapshot(before_fields)
    after_fields = _updated_state_fields(
        before_fields=before_fields,
        channel=channel,
        mapping=mapping,
        state=state,
        reason=command.reason,
        options=options,
    )
    after = _snapshot(after_fields)

    if not options.dry_run:
        _write_state_file(state_file, after_fields)
    verification.append(_verification("state_written", not options.dry_run))

    return {
        "schema": _SCHEMA,
        "version": 1,
        "ok": True,
        "operation": "write-state",
        "source_type": "mapped-project",
        "command": {
            "type": "set-state",
            "raw": options.raw_command,
            "state": state,
            "reason": command.reason,
            "reason_supplied": bool(command.reason),
        },
        "channel": _channel_packet(channel),
        "project": {
            "folder": str(project_path),
            "state_file": str(state_file),
            "git_top_level": str(git_top_level),
            "git_boundary_ok": git_boundary_ok,
            "git_clean": _git_clean(project_path),
        },
        "target_paths": [str(state_file)],
        "before": before,
        "after": after,
        "verification": verification,
        "commit_required": not options.dry_run,
        "dry_run": options.dry_run,
        "warnings": [],
        "errors": [],
        "proposed_external_actions": [],
    }


def read_mapped_project_lifecycle_state(
    channel: CurrentChannelContext,
    mapping: SafeProjectMapping,
    command: StateStatusCommand | None = None,
    *,
    raw_command: str = "",
) -> dict[str, Any]:
    """Read `LIFECYCLE_STATE.md` for a safely mapped project channel."""

    if mapping.channel_id != channel.channel_id:
        raise MappedProjectStateError(
            f"Mapping channel id does not match current channel {channel.channel_id!r}"
        )

    project_path = Path(mapping.project_path).resolve()
    state_file = project_path / "LIFECYCLE_STATE.md"

    verification = [_verification("mapped_project_exists", project_path.is_dir())]
    if not project_path.is_dir():
        raise MappedProjectStateError(f"Mapped project folder does not exist: {project_path}")

    git_top_level = _git_top_level(project_path)
    git_boundary_ok = git_top_level == project_path
    verification.append(_verification("git_top_level_is_project", git_boundary_ok))
    if not git_boundary_ok:
        raise MappedProjectStateError(
            f"Mapped project git top-level is {git_top_level}, expected {project_path}"
        )

    fields = _read_state_file(state_file)
    after = _snapshot(fields)
    verification.append(_verification("state_read", state_file.exists()))

    return {
        "schema": _SCHEMA,
        "version": 1,
        "ok": True,
        "operation": "read-status",
        "source_type": "mapped-project",
        "command": {
            "type": "status",
            "raw": raw_command,
        },
        "channel": _channel_packet(channel),
        "project": {
            "folder": str(project_path),
            "state_file": str(state_file),
            "git_top_level": str(git_top_level),
            "git_boundary_ok": git_boundary_ok,
            "git_clean": _git_clean(project_path),
        },
        "target_paths": [str(state_file)],
        "before": None,
        "after": after,
        "verification": verification,
        "commit_required": False,
        "dry_run": False,
        "warnings": [],
        "errors": [],
        "proposed_external_actions": [],
    }


def _updated_state_fields(
    *,
    before_fields: Mapping[str, str],
    channel: CurrentChannelContext,
    mapping: SafeProjectMapping,
    state: str,
    reason: str,
    options: MappedProjectWriteOptions,
) -> dict[str, str]:
    now = options.now
    previous_state = before_fields.get("state", "")
    today = now.date().isoformat()

    fields = dict(before_fields)
    fields.update(
        {
            "state": state,
            "since": before_fields.get("since", today)
            if previous_state == state
            else today,
            "channel_id": channel.channel_id,
            "updated_by": options.actor,
            "reason": reason or f"state set to {state}",
            "source": options.source,
            "updated_at": now.isoformat(),
            "mapped_project": mapping.project_folder,
        }
    )
    if mapping.channel_name:
        fields.setdefault("canonical_slug", mapping.channel_name)
    return fields


def _read_state_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key:
            fields[key] = _unquote(value.strip())
    if "state" in fields:
        validate_state(fields["state"])
    return fields


def _write_state_file(path: Path, fields: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered_keys = [key for key in _REQUIRED_WRITE_KEYS if key in fields]
    ordered_keys.extend(
        key for key in fields if key not in ordered_keys and key != "mapped_project"
    )
    if "mapped_project" in fields:
        ordered_keys.append("mapped_project")

    lines = [_TITLE, ""]
    for key in ordered_keys:
        lines.append(f"{key}: {_format_value(key, fields[key])}")
    lines.append("")

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(path)


def _snapshot(fields: Mapping[str, str]) -> dict[str, str] | None:
    if not fields:
        return None
    snapshot = {
        "state": validate_state(fields.get("state", "")),
        "reason": fields.get("reason", ""),
        "source": fields.get("source", ""),
    }
    for key in ("since", "channel_id", "updated_by", "updated_at"):
        if fields.get(key):
            snapshot[key] = fields[key]
    return snapshot


def _verification(check: str, ok: bool) -> dict[str, Any]:
    return {"check": check, "ok": ok}


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


def _git_top_level(path: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        stderr = error.stderr.strip()
        raise MappedProjectStateError(
            f"Could not verify mapped project git boundary: {stderr}"
        ) from error
    return Path(result.stdout.strip()).resolve()


def _git_clean(path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == ""


def _format_value(key: str, value: str) -> str:
    if key in {"state", "since", "source", "updated_at", "next_review"}:
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value
