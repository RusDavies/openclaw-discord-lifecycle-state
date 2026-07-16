"""Pinned Discord lifecycle status message projection."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .context import CurrentChannelContext
from .status import read_lifecycle_state

_RESULT_SCHEMA = "openclaw.lifecycle.pinned_status_projection.v1"
_REGISTRY_SCHEMA = "openclaw.lifecycle.pinned_status_registry.v1"
MANAGED_FOOTER = "Managed by OpenClaw lifecycle projection."


class PinnedStatusProjectionError(ValueError):
    """Raised when a pinned status projection cannot be planned or applied safely."""


@dataclass(frozen=True)
class PinnedStatusProjectionOptions:
    """Options for pinned lifecycle status projection planning."""

    now: datetime
    registry_path: str | Path
    workspace_root: str | Path | None = None
    raw_command: str = ""
    dry_run: bool = True


@dataclass(frozen=True)
class ManagedDiscordMessage:
    """Minimal existing Discord message metadata needed for safe edits."""

    message_id: str
    author_is_bot: bool
    content: str


@dataclass(frozen=True)
class PinnedStatusApplyCallables:
    """Discord side-effect callables supplied by runtime code."""

    send_message: Callable[[str], Mapping[str, Any]]
    pin_message: Callable[[str], Mapping[str, Any]]
    edit_message: Callable[[str, str], Mapping[str, Any]]
    fetch_message: Callable[[str], ManagedDiscordMessage | Mapping[str, Any] | None]


def plan_pinned_status_projection(
    channel: CurrentChannelContext,
    registry_path: str | Path,
    status_result: Mapping[str, Any],
    options: PinnedStatusProjectionOptions,
) -> dict[str, Any]:
    """Return proposed Discord actions for a managed pinned status message."""

    path = Path(registry_path)
    registry = _read_registry(path)
    entry = _channel_entry(registry.get("channels", {}).get(channel.channel_id))
    known_message_id = str(entry.get("message_id", "")).strip()
    message = format_pinned_status_message(status_result)
    proposed_actions = _proposed_actions(channel.channel_id, known_message_id, message)

    return {
        "schema": _RESULT_SCHEMA,
        "version": 1,
        "ok": True,
        "operation": "pin-status-message",
        "mode": "dry-run" if options.dry_run else "apply",
        "dry_run": options.dry_run,
        "command": {
            "type": "pin-lifecycle-status",
            "raw": options.raw_command,
        },
        "channel": _channel_packet(channel),
        "status": {
            "source_type": status_result.get("source_type", ""),
            "after": status_result.get("after"),
            "warnings": list(status_result.get("warnings", [])),
        },
        "registry": {
            "path": str(path),
            "entry_key": channel.channel_id,
            "known_message_id": known_message_id,
        },
        "target_paths": [str(path)],
        "managed_message": {
            "message_id": known_message_id,
            "content": message,
            "footer": MANAGED_FOOTER,
        },
        "proposed_external_actions": proposed_actions,
        "verification": [
            {"check": "state_read", "ok": status_result.get("after") is not None},
            {"check": "state_command_side_effect_free", "ok": True},
            {"check": "managed_message_id_not_in_lifecycle_state", "ok": True},
        ],
        "commit_required": False,
        "warnings": list(status_result.get("warnings", [])),
        "errors": [],
    }


def handle_pinned_status_projection(
    channel: CurrentChannelContext,
    lookup_mapping: Any,
    lifecycle_registry_path: str | Path,
    options: PinnedStatusProjectionOptions,
    *,
    apply_callables: PinnedStatusApplyCallables | None = None,
) -> dict[str, Any]:
    """Plan or explicitly apply a managed pinned lifecycle status message."""

    status_result = read_lifecycle_state(
        channel,
        lifecycle_registry_path,
        mapping=lookup_mapping,
        raw_command=options.raw_command,
    )
    result = plan_pinned_status_projection(
        channel,
        options.registry_path,
        status_result,
        options,
    )
    if options.dry_run:
        result["message"] = format_pinned_status_projection_response(result)
        return result

    if apply_callables is None:
        raise PinnedStatusProjectionError("Apply requires Discord side-effect callables")

    applied = _apply_projection(result, options, apply_callables)
    applied["message"] = format_pinned_status_projection_response(applied)
    return applied


def format_pinned_status_message(status_result: Mapping[str, Any]) -> str:
    """Format the managed pinned lifecycle status message body."""

    after = status_result.get("after")
    source = _storage_text(status_result)
    if not isinstance(after, Mapping):
        lines = ["Lifecycle: unrecorded"]
        if source:
            lines.append(f"Source: {source}")
        lines.append(MANAGED_FOOTER)
        return "\n".join(lines)

    state = _optional_text(after.get("state")) or "unrecorded"
    lines = [f"Lifecycle: {state}"]

    reason = _optional_text(after.get("reason"))
    if reason:
        lines.append(f"Reason: {reason}")

    since = _optional_text(after.get("since"))
    if since:
        lines.append(f"Since: {since}")

    updated_at = _optional_text(after.get("updated_at"))
    if updated_at:
        lines.append(f"Updated: {updated_at}")

    if source:
        lines.append(f"Source: {source}")

    lines.append(MANAGED_FOOTER)
    return "\n".join(lines)


def format_pinned_status_projection_response(result: Mapping[str, Any]) -> str:
    """Format a concise visible response for pin projection dry-run/apply."""

    mode = result.get("mode")
    actions = result.get("proposed_external_actions")
    if not isinstance(actions, list):
        raise PinnedStatusProjectionError("Projection result actions must be a list")

    if mode == "apply":
        message_id = ""
        applied = result.get("applied")
        if isinstance(applied, Mapping):
            message_id = _optional_text(applied.get("message_id"))
        lines = ["Pinned lifecycle status message updated."]
        if message_id:
            lines.append(f"Managed message: `{message_id}`")
    else:
        lines = ["Pinned lifecycle status dry-run."]

    lines.append("Proposed Discord actions:")
    for action in actions:
        if isinstance(action, Mapping):
            lines.append(f"- {action.get('action', 'unknown')}")

    for warning in result.get("warnings", []):
        if isinstance(warning, str) and warning.strip():
            lines.append(f"Warning: {warning.strip()}")
    return "\n".join(lines)


def _apply_projection(
    result: dict[str, Any],
    options: PinnedStatusProjectionOptions,
    callables: PinnedStatusApplyCallables,
) -> dict[str, Any]:
    message = str(result["managed_message"]["content"])
    known_message_id = str(result["registry"]["known_message_id"])

    if known_message_id:
        existing = _managed_message(callables.fetch_message(known_message_id))
        _verify_managed_existing_message(existing)
        edit_receipt = callables.edit_message(known_message_id, message)
        pin_receipt = callables.pin_message(known_message_id)
        message_id = known_message_id
        receipts = {"edit": edit_receipt, "pin": pin_receipt}
    else:
        send_receipt = callables.send_message(message)
        message_id = _message_id_from_receipt(send_receipt)
        if not message_id:
            raise PinnedStatusProjectionError(
                "Could not determine managed message id from send receipt"
            )
        pin_receipt = callables.pin_message(message_id)
        receipts = {"send": send_receipt, "pin": pin_receipt}

    _write_registry_entry(
        Path(options.registry_path),
        result["channel"],
        message_id,
        options.now,
    )
    result["mode"] = "apply"
    result["dry_run"] = False
    result["applied"] = {
        "message_id": message_id,
        "receipts": receipts,
        "registry_updated": True,
    }
    return result


def _verify_managed_existing_message(message: ManagedDiscordMessage) -> None:
    if not message.message_id:
        raise PinnedStatusProjectionError("Managed message id is missing")
    if not message.author_is_bot:
        raise PinnedStatusProjectionError("Refusing to edit a non-bot Discord message")
    if MANAGED_FOOTER not in message.content:
        raise PinnedStatusProjectionError(
            "Refusing to edit a message without the lifecycle managed footer"
        )


def _managed_message(value: ManagedDiscordMessage | Mapping[str, Any] | None) -> ManagedDiscordMessage:
    if isinstance(value, ManagedDiscordMessage):
        return value
    if isinstance(value, Mapping):
        return ManagedDiscordMessage(
            message_id=_optional_text(value.get("message_id") or value.get("id")),
            author_is_bot=bool(value.get("author_is_bot") or value.get("bot")),
            content=_optional_text(value.get("content")),
        )
    return ManagedDiscordMessage(message_id="", author_is_bot=False, content="")


def _message_id_from_receipt(receipt: Mapping[str, Any]) -> str:
    for key in ("messageId", "message_id", "platformMessageId"):
        value = _optional_text(receipt.get(key))
        if value:
            return value
    nested = receipt.get("receipt")
    if isinstance(nested, Mapping):
        raw_parts = nested.get("raw")
        if isinstance(raw_parts, list):
            for item in raw_parts:
                if isinstance(item, Mapping):
                    value = _optional_text(item.get("messageId") or item.get("message_id"))
                    if value:
                        return value
        parts = nested.get("parts")
        if isinstance(parts, list):
            for item in parts:
                if isinstance(item, Mapping):
                    value = _optional_text(item.get("platformMessageId"))
                    if value:
                        return value
    return ""


def _proposed_actions(channel_id: str, message_id: str, message: str) -> list[dict[str, Any]]:
    if message_id:
        return [
            {
                "action": "edit",
                "channel": "discord",
                "channelId": channel_id,
                "messageId": message_id,
                "message": message,
            },
            {
                "action": "pin",
                "channel": "discord",
                "channelId": channel_id,
                "messageId": message_id,
            },
        ]
    return [
        {
            "action": "send",
            "channel": "discord",
            "channelId": channel_id,
            "message": message,
        },
        {
            "action": "pin",
            "channel": "discord",
            "channelId": channel_id,
            "messageId": "<message-id-from-send>",
        },
    ]


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
        raise PinnedStatusProjectionError(f"Projection registry JSON is invalid: {error}") from error
    if not isinstance(registry, dict):
        raise PinnedStatusProjectionError("Projection registry must be a JSON object")
    if registry.get("schema") != _REGISTRY_SCHEMA:
        raise PinnedStatusProjectionError("Projection registry schema is unsupported or missing")
    if registry.get("version") != 1:
        raise PinnedStatusProjectionError("Projection registry version is unsupported or missing")
    registry.setdefault("channels", {})
    return registry


def _write_registry_entry(
    path: Path,
    channel_packet: Mapping[str, Any],
    message_id: str,
    now: datetime,
) -> None:
    registry = _read_registry(path)
    channels = registry.setdefault("channels", {})
    if not isinstance(channels, dict):
        raise PinnedStatusProjectionError("Projection registry channels field must be an object")
    channel_id = str(channel_packet.get("channel_id", ""))
    entry = {
        "channel_id": channel_id,
        "message_id": message_id,
        "updated_at": now.isoformat(),
        "managed_footer": MANAGED_FOOTER,
    }
    channel_name = _optional_text(channel_packet.get("channel_name"))
    if channel_name:
        entry["channel_name"] = channel_name
    channels[channel_id] = entry
    registry["updated_at"] = now.isoformat()
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
        raise PinnedStatusProjectionError("Projection registry channel entry must be an object")
    return value


def _storage_text(result: Mapping[str, Any]) -> str:
    source_type = result.get("source_type")
    if source_type == "mapped-project":
        return "mapped project LIFECYCLE_STATE.md"
    if source_type == "channel-local-registry":
        return "channel-local registry"
    return ""


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


def _optional_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
