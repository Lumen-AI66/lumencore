from __future__ import annotations

def check_owner_approval(owner_approved: bool) -> tuple[bool, str]:
    if not owner_approved:
        return False, "owner approval required"
    return True, "owner approval granted"
