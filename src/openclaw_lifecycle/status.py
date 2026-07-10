"""Lifecycle state status reads with mapped-project precedence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .commands import StateStatusCommand
from .context import CurrentChannelContext
from .mapping import SafeProjectMapping
from .project_state import read_mapped_project_lifecycle_state
from .registry_state import read_channel_registry_lifecycle_state


def read_lifecycle_state(
    channel: CurrentChannelContext,
    registry_path: str | Path,
    command: StateStatusCommand | None = None,
    *,
    mapping: SafeProjectMapping | None = None,
    raw_command: str = "",
) -> dict[str, Any]:
    """Read lifecycle state, preferring mapped project state when available."""

    status_command = command or StateStatusCommand()
    if mapping is None:
        return read_channel_registry_lifecycle_state(
            channel,
            registry_path,
            status_command,
            raw_command=raw_command,
        )

    result = read_mapped_project_lifecycle_state(
        channel,
        mapping,
        status_command,
        raw_command=raw_command,
    )
    registry_result = read_channel_registry_lifecycle_state(
        channel,
        registry_path,
        status_command,
        raw_command=raw_command,
    )
    if registry_result["after"] is not None:
        result["warnings"].append(
            "Channel-local registry state also exists; mapped project state takes precedence."
        )
        result["target_paths"].extend(registry_result["target_paths"])
    return result
