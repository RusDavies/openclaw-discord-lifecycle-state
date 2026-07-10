"""OpenClaw lifecycle-state helpers."""

from .adapter import (
    ChannelLookupPacketError,
    ChannelLookupResolution,
    resolve_channel_lookup_packet,
)
from .commands import (
    LifecycleCommand,
    LifecycleCommandError,
    StateSetCommand,
    StateStatusCommand,
    parse_lifecycle_command,
    parse_state_set_command,
    parse_state_status_command,
)
from .context import (
    ChannelContextError,
    CurrentChannelContext,
    resolve_current_channel_context,
)
from .discord_response import (
    LifecycleResponseError,
    format_lifecycle_command_error,
    format_state_status_response,
    format_state_write_confirmation,
)
from .mapping import (
    ProjectMappingError,
    SafeProjectMapping,
    resolve_safe_project_mapping,
)
from .project_state import (
    MappedProjectStateError,
    MappedProjectWriteOptions,
    read_mapped_project_lifecycle_state,
    write_mapped_project_lifecycle_state,
)
from .registry_state import (
    ChannelRegistryStateError,
    ChannelRegistryWriteOptions,
    read_channel_registry_lifecycle_state,
    write_channel_registry_lifecycle_state,
)
from .status import read_lifecycle_state
from .state import (
    ALLOWED_STATES,
    LifecycleStateError,
    allowed_states_text,
    is_valid_state,
    validate_state,
)
from .workflow import (
    LifecycleWorkflowError,
    LifecycleWorkflowOptions,
    handle_lifecycle_command,
)

__all__ = [
    "ALLOWED_STATES",
    "ChannelContextError",
    "ChannelLookupPacketError",
    "ChannelLookupResolution",
    "ChannelRegistryStateError",
    "ChannelRegistryWriteOptions",
    "CurrentChannelContext",
    "LifecycleCommand",
    "LifecycleCommandError",
    "LifecycleResponseError",
    "LifecycleStateError",
    "LifecycleWorkflowError",
    "LifecycleWorkflowOptions",
    "MappedProjectStateError",
    "MappedProjectWriteOptions",
    "ProjectMappingError",
    "SafeProjectMapping",
    "StateSetCommand",
    "StateStatusCommand",
    "allowed_states_text",
    "format_lifecycle_command_error",
    "format_state_status_response",
    "format_state_write_confirmation",
    "handle_lifecycle_command",
    "is_valid_state",
    "parse_lifecycle_command",
    "parse_state_set_command",
    "parse_state_status_command",
    "read_channel_registry_lifecycle_state",
    "read_lifecycle_state",
    "read_mapped_project_lifecycle_state",
    "resolve_channel_lookup_packet",
    "resolve_current_channel_context",
    "resolve_safe_project_mapping",
    "validate_state",
    "write_channel_registry_lifecycle_state",
    "write_mapped_project_lifecycle_state",
]
