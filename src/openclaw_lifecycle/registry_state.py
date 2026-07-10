"""Channel-local lifecycle registry writes for unmapped Discord channels."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .commands import StateSetCommand
from .context import CurrentChannelContext
from .state import validate_state

_COMMAND_RESULT_SCHEMA = "openclaw.lifecycle.command_result.v1"
_REGISTRY_SCHEMA = "openclaw.lifecycle.channel_registry.v1"


class ChannelRegistryStateError(ValueError):
    """Raised when channel-local lifecycle registry state cannot be written."""


@dataclass(frozen=True)
class ChannelRegistryWriteOptions:
    """Metadata for a channel-local lifecycle registry write."""

    actor: str
    now: datetime
    raw_command: str = ""
    source: str = "discord-command"
    dry_run: bool = False


def write_channel_registry_lifecycle_state(
    channel: CurrentChannelContext,
    registry_path: str | Path,
    command: StateSetCommand,
    options: ChannelRegistryWriteOptions,
) -> dict[str, Any]:
    """Write lifecycle state for an unmapped channel registry entry."""

    state = validate_state(command.state)
    path = Path(registry_path)
    registry = _read_registry(path)
    channels = registry.setdefault("channels", {})
    if not isinstance(channels, dict):
        raise ChannelRegistryStateError("Registry channels field must be an object")

    before_entry = _channel_entry(channels.get(channel.channel_id))
    before = _snapshot(before_entry)
    after_entry = _updated_entry(
        before_entry=before_entry,
        channel=channel,
        state=state,
        reason=command.reason,
        options=options,
    )
    after = _snapshot(after_entry)

    if not options.dry_run:
        channels[channel.channel_id] = after_entry
        registry["updated_at"] = options.now.isoformat()
        _write_registry(path, registry)

    return {
        "schema": _COMMAND_RESULT_SCHEMA,
        "version": 1,
        "ok": True,
        "operation": "write-state",
        "source_type": "channel-local-registry",
        "command": {
            "type": "set-state",
            "raw": options.raw_command,
            "state": state,
            "reason": command.reason,
            "reason_supplied": bool(command.reason),
        },
        "channel": _channel_packet(channel),
        "registry": {
            "path": str(path),
            "entry_key": channel.channel_id,
        },
        "target_paths": [str(path)],
        "before": before,
        "after": after,
        "verification": [
            {"check": "channel_id_present", "ok": bool(channel.channel_id)},
            {"check": "registry_path_available", "ok": True},
            {"check": "state_written", "ok": not options.dry_run},
        ],
        "commit_required": False,
        "dry_run": options.dry_run,
        "warnings": [],
        "errors": [],
        "proposed_external_actions": [],
    }


def _read_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema": _REGISTRY_SCHEMA,
            "version": 1,
            "updated_at": "",
            "channels": {},
        }

    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ChannelRegistryStateError(f"Registry JSON is invalid: {error}") from error

    if not isinstance(registry, dict):
        raise ChannelRegistryStateError("Registry must be a JSON object")
    if registry.get("schema") != _REGISTRY_SCHEMA:
        raise ChannelRegistryStateError("Registry schema is unsupported or missing")
    if registry.get("version") != 1:
        raise ChannelRegistryStateError("Registry version is unsupported or missing")
    if "channels" not in registry:
        registry["channels"] = {}
    return registry


def _updated_entry(
    *,
    before_entry: Mapping[str, Any],
    channel: CurrentChannelContext,
    state: str,
    reason: str,
    options: ChannelRegistryWriteOptions,
) -> dict[str, Any]:
    now = options.now
    today = now.date().isoformat()
    previous_state = str(before_entry.get("state", ""))

    entry = dict(before_entry)
    entry.update(
        {
            "channel_id": channel.channel_id,
            "state": state,
            "since": before_entry.get("since", today)
            if previous_state == state
            else today,
            "updated_at": now.isoformat(),
            "updated_by": options.actor,
            "reason": reason or f"state set to {state}",
            "source": options.source,
            "mapping_status": "unmapped",
        }
    )

    for key in (
        "guild_id",
        "guild_name",
        "channel_name",
        "category_id",
        "category_name",
    ):
        value = getattr(channel, key)
        if value:
            entry[key] = value

    return entry


def _write_registry(path: Path, registry: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _channel_entry(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ChannelRegistryStateError("Registry channel entry must be an object")
    if "state" in value:
        validate_state(str(value["state"]))
    return value


def _snapshot(entry: Mapping[str, Any]) -> dict[str, str] | None:
    if not entry:
        return None
    snapshot = {
        "state": validate_state(str(entry.get("state", ""))),
        "reason": str(entry.get("reason", "")),
        "source": str(entry.get("source", "")),
    }
    for key in ("since", "channel_id", "updated_by", "updated_at"):
        if entry.get(key):
            snapshot[key] = str(entry[key])
    return snapshot


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
