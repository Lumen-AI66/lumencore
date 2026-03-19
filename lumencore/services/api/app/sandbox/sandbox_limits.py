from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxLimits:
    filesystem_write_allowed: bool = False
    subprocess_allowed: bool = False
    network_allowed: bool = False
    os_command_allowed: bool = False
