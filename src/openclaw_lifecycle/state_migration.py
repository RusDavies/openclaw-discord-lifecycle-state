"""Migration from channel-local registry state to mapped project state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import subprocess
from typing import Any

from .commands import MigrateStateHereCommand
from .context import CurrentChannelContext
from .mapping import SafeProjectMapping
from .state import validate_state

_COMMAND_RESULT_SCHEMA = "openclaw.lifecycle.command_result.v1"
_REGISTRY_SCHEMA = "openclaw.lifecycle.channel_registry.v1"
_TITLE = "# Lifecycle State"


class StateMigrationError(ValueError):
    """Raised when registry-to-project migration cannot run safely."""


@dataclass(frozen=True)
class StateMigrationOptions:
    """Runtime options for `migrate state here`."""

    actor: str
    now: datetime
    registry_path: str | Path
    raw_command: str = ""
    dry_run: bool = False


def migrate_registry_state_to_project(
    channel: CurrentChannelContext,
    mapping: SafeProjectMapping | None,
    command: MigrateStateHereCommand,
    options: StateMigrationOptions,
) -> dict[str, Any]:
    """Copy channel-local registry state into mapped `LIFECYCLE_STATE.md`."""

    if mapping is None:
        raise StateMigrationError("Cannot migrate state without a safe project mapping")
    if mapping.channel_id != channel.channel_id:
        raise StateMigrationError(
            f"Mapping channel id does not match current channel {channel.channel_id!r}"
        )

    registry_path = Path(options.registry_path)
    registry = _read_registry(registry_path)
    channels = registry.setdefault("channels", {})
    if not isinstance(channels, dict):
        raise StateMigrationError("Registry channels field must be an object")
    registry_entry = _registry_entry(channels.get(channel.channel_id))
    if not registry_entry:
        raise StateMigrationError("No channel-local registry state exists to migrate")

    state = validate_state(str(registry_entry.get("state", "")))
    project_path = Path(mapping.project_path).resolve()
    state_file = project_path / "LIFECYCLE_STATE.md"
    _verify_project(project_path)

    before_project = _snapshot(_read_state_file(state_file))
    before_registry = _registry_snapshot(registry_entry)
    after_fields = _migrated_project_fields(
        before_fields=_read_state_file(state_file),
        channel=channel,
        mapping=mapping,
        registry_entry=registry_entry,
        state=state,
        options=options,
    )
    after_project = _snapshot(after_fields)
    after_registry_entry = _mapped_shadow_entry(
        registry_entry=registry_entry,
        mapping=mapping,
        options=options,
    )
    after_registry = _registry_snapshot(after_registry_entry)

    if not options.dry_run:
        _write_state_file(state_file, after_fields)
        channels[channel.channel_id] = after_registry_entry
        registry["updated_at"] = options.now.isoformat()
        _write_registry(registry_path, registry)

    return {
        "schema": _COMMAND_RESULT_SCHEMA,
        "version": 1,
        "ok": True,
        "operation": "migrate-registry-state",
        "source_type": "registry-to-mapped-project",
        "command": {
            "type": "migrate-state",
            "raw": options.raw_command,
        },
        "channel": _channel_packet(channel),
        "project": {
            "folder": str(project_path),
            "state_file": str(state_file),
            "git_top_level": str(_git_top_level(project_path)),
            "git_boundary_ok": True,
            "git_clean": _git_clean(project_path),
        },
        "registry": {
            "path": str(registry_path),
            "entry_key": channel.channel_id,
        },
        "target_paths": [str(state_file), str(registry_path)],
        "before": {
            "project": before_project,
            "registry": before_registry,
        },
        "after": {
            "project": after_project,
            "registry": after_registry,
        },
        "verification": [
            {"check": "mapped_project_exists", "ok": project_path.is_dir()},
            {"check": "git_top_level_is_project", "ok": True},
            {"check": "registry_entry_exists", "ok": True},
            {"check": "state_migrated", "ok": not options.dry_run},
        ],
        "commit_required": not options.dry_run,
        "dry_run": options.dry_run,
        "warnings": [],
        "errors": [],
        "proposed_external_actions": [],
    }


def format_state_migration_response(result: Mapping[str, Any]) -> str:
    """Format a concise Discord response for state migration."""

    after = _mapping(result.get("after"))
    project_after = _mapping(after.get("project"))
    registry_after = _mapping(after.get("registry"))
    project = _mapping(result.get("project"))
    lines = [
        f"Migrated registry state to mapped project: `{project_after.get('state', '')}`",
    ]
    reason = project_after.get("reason")
    if reason:
        lines.append(f"Reason: {reason}")
    lines.append(f"Stored: `{project.get('state_file', '')}`")
    if registry_after.get("mapping_status"):
        lines.append(f"Registry marked: `{registry_after.get('mapping_status')}`")
    if result.get("commit_required"):
        lines.append("Project commit required.")
    return "\n".join(lines)


def _read_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise StateMigrationError("Channel-local registry does not exist")
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise StateMigrationError(f"Registry JSON is invalid: {error}") from error
    if not isinstance(registry, dict):
        raise StateMigrationError("Registry must be a JSON object")
    if registry.get("schema") != _REGISTRY_SCHEMA:
        raise StateMigrationError("Registry schema is unsupported or missing")
    if registry.get("version") != 1:
        raise StateMigrationError("Registry version is unsupported or missing")
    return registry


def _write_registry(path: Path, registry: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _registry_entry(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise StateMigrationError("Registry channel entry must be an object")
    if "state" in value:
        validate_state(str(value["state"]))
    return dict(value)


def _verify_project(project_path: Path) -> None:
    if not project_path.is_dir():
        raise StateMigrationError(f"Mapped project folder does not exist: {project_path}")
    git_top_level = _git_top_level(project_path)
    if git_top_level != project_path:
        raise StateMigrationError(
            f"Mapped project git top-level is {git_top_level}, expected {project_path}"
        )


def _git_top_level(project_path: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=project_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise StateMigrationError(result.stderr.strip() or "Project is not a git repository")
    return Path(result.stdout.strip()).resolve()


def _git_clean(project_path: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=project_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode == 0 and not result.stdout.strip()


def _read_state_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().casefold().replace(" ", "_")
        if key:
            fields[key] = _unquote(value.strip())
    if "state" in fields:
        fields["state"] = validate_state(fields["state"].casefold())
    return fields


def _migrated_project_fields(
    *,
    before_fields: Mapping[str, str],
    channel: CurrentChannelContext,
    mapping: SafeProjectMapping,
    registry_entry: Mapping[str, Any],
    state: str,
    options: StateMigrationOptions,
) -> dict[str, str]:
    fields = dict(before_fields)
    fields.update(
        {
            "state": state,
            "since": str(registry_entry.get("since", "")) or options.now.date().isoformat(),
            "channel_id": channel.channel_id,
            "updated_by": options.actor,
            "reason": str(registry_entry.get("reason", "")) or f"state set to {state}",
            "source": "registry-migration",
            "updated_at": options.now.isoformat(),
            "mapped_project": mapping.project_folder,
            "migrated_from_registry_at": options.now.isoformat(),
        }
    )
    if mapping.channel_name:
        fields.setdefault("canonical_slug", mapping.channel_name)
    return fields


def _mapped_shadow_entry(
    *,
    registry_entry: Mapping[str, Any],
    mapping: SafeProjectMapping,
    options: StateMigrationOptions,
) -> dict[str, Any]:
    entry = dict(registry_entry)
    entry.update(
        {
            "mapping_status": "mapped-shadow",
            "mapped_project": mapping.project_folder,
            "migrated_at": options.now.isoformat(),
            "migration_source": "migrate-state-here",
        }
    )
    return entry


def _write_state_file(path: Path, fields: Mapping[str, str]) -> None:
    ordered = [
        "state",
        "since",
        "channel_id",
        "updated_by",
        "reason",
        "source",
        "updated_at",
    ]
    ordered.extend(key for key in fields if key not in ordered and key != "mapped_project")
    if "mapped_project" in fields:
        ordered.append("mapped_project")

    lines = [_TITLE, ""]
    for key in ordered:
        lines.append(f"{key}: {_format_value(key, fields[key])}")
    lines.append("")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(path)


def _snapshot(fields: Mapping[str, str]) -> dict[str, str] | None:
    if not fields or not fields.get("state"):
        return None
    snapshot = {
        "state": validate_state(str(fields.get("state", ""))),
        "reason": str(fields.get("reason", "")),
        "source": str(fields.get("source", "")),
    }
    for key in ("since", "channel_id", "updated_by", "updated_at"):
        if fields.get(key):
            snapshot[key] = str(fields[key])
    return snapshot


def _registry_snapshot(entry: Mapping[str, Any]) -> dict[str, str]:
    snapshot = {
        "state": validate_state(str(entry.get("state", ""))),
        "reason": str(entry.get("reason", "")),
        "source": str(entry.get("source", "")),
        "mapping_status": str(entry.get("mapping_status", "")),
    }
    for key in ("since", "channel_id", "updated_by", "updated_at", "mapped_project", "migrated_at"):
        if entry.get(key):
            snapshot[key] = str(entry[key])
    return snapshot


def _format_value(key: str, value: str) -> str:
    if key in {"reason", "channel_id", "updated_by", "canonical_slug", "mapped_project"}:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _channel_packet(channel: CurrentChannelContext) -> dict[str, str]:
    packet = {"channel_id": channel.channel_id}
    if channel.channel_name:
        packet["channel_name"] = channel.channel_name
    if channel.guild_id:
        packet["guild_id"] = channel.guild_id
    return packet
