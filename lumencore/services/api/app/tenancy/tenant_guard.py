from __future__ import annotations


def normalize_tenant_id(tenant_id: str | None) -> str:
    return (tenant_id or 'owner').strip() or 'owner'


_ALLOWED_TENANTS = frozenset({'owner', 'telegram'})


def enforce_owner_tenant(tenant_id: str | None) -> str:
    normalized = normalize_tenant_id(tenant_id)
    if normalized not in _ALLOWED_TENANTS:
        raise ValueError('only owner tenant is enabled in current phase')
    return normalized
