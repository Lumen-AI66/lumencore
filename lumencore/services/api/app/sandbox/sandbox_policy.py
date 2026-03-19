from __future__ import annotations

from .sandbox_limits import SandboxLimits
from .sandbox_profiles import SANDBOX_PROFILES


DEFAULT_SANDBOX_PROFILE = 'read_only'


def sandbox_limits_for_profile(profile: str | None) -> SandboxLimits:
    key = (profile or DEFAULT_SANDBOX_PROFILE).strip() or DEFAULT_SANDBOX_PROFILE
    return SANDBOX_PROFILES.get(key, SANDBOX_PROFILES[DEFAULT_SANDBOX_PROFILE])


def default_sandbox_limits() -> SandboxLimits:
    return sandbox_limits_for_profile(DEFAULT_SANDBOX_PROFILE)
