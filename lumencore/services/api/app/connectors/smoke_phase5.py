from __future__ import annotations

from app.connectors.audit.connector_audit import get_connector_metrics
from app.connectors.base.registry import list_connectors
from app.connectors.connector_service import execute_connector_request
from app.connectors.policy.connector_policy import load_connector_enablement
from app.connectors.startup import register_default_connectors


def run() -> None:
    register_default_connectors()
    names = {item["connector_name"] for item in list_connectors()}
    assert "git" in names, "git connector not registered"
    assert "search" in names, "search connector not registered"

    enablement = load_connector_enablement()
    assert enablement.get("git") is False, "git must be disabled by default"
    assert enablement.get("search") is False, "search must be disabled by default"

    captured: list[dict] = []

    def writer(event: dict) -> None:
        captured.append(event)

    result = execute_connector_request(
        connector_name="git",
        payload={"action": "clone_repo", "repo_url": "https://example.invalid/repo.git"},
        tenant_id="owner",
        project_id="default",
        agent_id="agent-1",
        audit_writer=writer,
    )

    assert not result.allowed, "disabled connector should be denied"
    assert len(captured) == 2, "expected exactly connector.call + connector.denied"
    assert any(e.get("action") == "connector.call" for e in captured), "missing connector.call audit event"
    assert any(e.get("action") == "connector.denied" for e in captured), "missing connector.denied audit event"

    for event in captured:
        # Connector events are shaped for the existing audit pipeline fields.
        assert "tenant_id" in event
        assert "action" in event
        assert "policy_result" in event
        assert "metadata" in event

    metrics = get_connector_metrics()
    assert metrics["connector_calls_total"] >= 1, "connector_calls_total not incremented"
    assert metrics["connector_denied_total"] >= 1, "connector_denied_total not incremented"

    print("Phase 5 connector smoke checks passed")


if __name__ == "__main__":
    run()
