"""Current Discord channel context resolution."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
import re
from typing import Any

_SNOWFLAKE_RE = re.compile(r"^[0-9]{17,20}$")
_CHANNEL_ID_IN_TEXT_RE = re.compile(r"\bchannel id:([0-9]{17,20})\b", re.IGNORECASE)


class ChannelContextError(ValueError):
    """Raised when current channel context cannot be resolved."""


@dataclass(frozen=True)
class CurrentChannelContext:
    """Resolved Discord channel context for a lifecycle command."""

    channel_id: str
    channel_name: str = ""
    guild_id: str = ""
    guild_name: str = ""
    category_id: str = ""
    category_name: str = ""
    topic: str = ""


def resolve_current_channel_context(
    conversation_info: Mapping[str, Any],
    channel_metadata: Mapping[str, Any] | None = None,
) -> CurrentChannelContext:
    """Resolve current Discord channel context from runtime metadata.

    `conversation_info` is expected to be trusted runtime metadata for the
    current Discord delivery, not text parsed from a user message.
    """

    channel_id = _resolve_channel_id(conversation_info)
    guild_id = _optional_snowflake(
        _first_text(conversation_info, "guild_id", "group_space", "guild")
    )
    payload = _metadata_payload(channel_metadata)

    return CurrentChannelContext(
        channel_id=channel_id,
        channel_name=_normalize_channel_name(
            _first_text(
                conversation_info,
                "channel_name",
                "group_channel",
                "group_subject",
            )
        ),
        guild_id=guild_id,
        guild_name=_first_text(conversation_info, "guild_name", "group_name"),
        category_id=_optional_snowflake(
            _first_text(conversation_info, "category_id", "parent_id")
        ),
        category_name=_first_text(conversation_info, "category_name"),
        topic=_first_text(payload, "topic"),
    )


def _resolve_channel_id(conversation_info: Mapping[str, Any]) -> str:
    candidates = (
        _first_text(conversation_info, "channel_id", "target_id"),
        _strip_channel_prefix(_first_text(conversation_info, "chat_id")),
        _channel_id_from_label(_first_text(conversation_info, "conversation_label")),
    )
    for candidate in candidates:
        if not candidate:
            continue
        if _SNOWFLAKE_RE.fullmatch(candidate):
            return candidate
        raise ChannelContextError(f"Invalid Discord channel id: {candidate!r}")

    raise ChannelContextError("Missing Discord channel id")


def _metadata_payload(channel_metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not channel_metadata:
        return {}
    payload = channel_metadata.get("payload")
    if isinstance(payload, Mapping):
        return payload
    return channel_metadata


def _first_text(mapping: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _optional_snowflake(value: str) -> str:
    if not value:
        return ""
    candidate = _strip_channel_prefix(value)
    if _SNOWFLAKE_RE.fullmatch(candidate):
        return candidate
    raise ChannelContextError(f"Invalid Discord snowflake: {value!r}")


def _strip_channel_prefix(value: str) -> str:
    if value.startswith("channel:"):
        return value.removeprefix("channel:").strip()
    return value.strip()


def _channel_id_from_label(value: str) -> str:
    match = _CHANNEL_ID_IN_TEXT_RE.search(value)
    return match.group(1) if match else ""


def _normalize_channel_name(value: str) -> str:
    return value.strip().lstrip("#").strip()
