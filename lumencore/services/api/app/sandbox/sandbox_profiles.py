from __future__ import annotations

from .sandbox_limits import SandboxLimits


SANDBOX_PROFILES: dict[str, SandboxLimits] = {
    'read_only': SandboxLimits(filesystem_write_allowed=False, subprocess_allowed=False, network_allowed=False, os_command_allowed=False),
    'agent_safe': SandboxLimits(filesystem_write_allowed=False, subprocess_allowed=False, network_allowed=False, os_command_allowed=False),
    'executor_extended': SandboxLimits(filesystem_write_allowed=False, subprocess_allowed=False, network_allowed=False, os_command_allowed=False),
}
