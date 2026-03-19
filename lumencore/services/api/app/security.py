from __future__ import annotations

"""
Phase 3C security boundary placeholders.

No authentication is enforced yet. These hooks centralize future Phase 8
internal-observability auth logic so endpoint wiring does not need redesign.
"""

from fastapi import Header, HTTPException


def internal_observability_boundary() -> None:
    # Intentionally no-op in Phase 3C.
    return None


def internal_route_boundary(x_lumencore_internal_route: str | None = Header(default=None)) -> None:
    if (x_lumencore_internal_route or "").strip().lower() == "true":
        return None
    raise HTTPException(
        status_code=403,
        detail={
            "error_code": "internal_route_required",
            "message": "this route is reserved for internal control-plane use",
            "canonical_route": "/api/command/run",
        },
    )
