"""Lifecycle command orchestration for current-channel state commands."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .adapter import resolve_channel_lookup_packet
from .commands import StateSetCommand, parse_lifecycle_command
from .context import CurrentChannelContext
from .project_state import (
    MappedProjectWriteOptions,
    write_mapped_project_lifecycle_state,
)
from .registry_state import (
    ChannelRegistryWriteOptions,
    write_channel_registry_lifecycle_state,
)
from .status import read_lifecycle_state


class LifecycleWorkflowError(ValueError):
    """Raised when a lifecycle command cannot select a safe storage source."""


@dataclass(frozen=True)
class LifecycleWorkflowOptions:
    """Runtime options for handling a lifecycle command."""

    actor: str
    now: datetime
    registry_path: str | Path
    workspace_root: str | Path | None = None


def handle_lifecycle_command(
    raw_command: str,
    channel: CurrentChannelContext,
    lookup_packet: Mapping[str, Any],
    options: LifecycleWorkflowOptions,
) -> dict[str, Any]:
    """Handle one parsed lifecycle command without performing Discord side effects."""

    command = parse_lifecycle_command(raw_command)
    lookup = resolve_channel_lookup_packet(
        channel,
        lookup_packet,
        workspace_root=options.workspace_root,
    )
    if lookup.status in {"ambiguous", "error"}:
        raise LifecycleWorkflowError(
            f"Cannot safely resolve lifecycle storage source: {lookup.status}"
        )

    if isinstance(command, StateSetCommand):
        if lookup.mapping is not None:
            return write_mapped_project_lifecycle_state(
                channel,
                lookup.mapping,
                command,
                MappedProjectWriteOptions(
                    actor=options.actor,
                    now=options.now,
                    raw_command=raw_command,
                ),
            )
        return write_channel_registry_lifecycle_state(
            channel,
            options.registry_path,
            command,
            ChannelRegistryWriteOptions(
                actor=options.actor,
                now=options.now,
                raw_command=raw_command,
            ),
        )

    return read_lifecycle_state(
        channel,
        options.registry_path,
        command,
        mapping=lookup.mapping,
        raw_command=raw_command,
    )
