from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes import agent as agent_route
from admin.api.routes.agent import get_agent_orchestrator, router


class _FakeAgent:
    def __init__(self):
        self.payload = None

    def ask(self, payload):
        self.payload = payload
        return {
            "status": "answered",
            "intent": "inventory_query",
            "answer": "结论\n\n依据\n\n后续动作",
            "citations": [],
            "related_records": [],
            "tool_trace": [{"tool": "ComplianceInventoryTool", "status": "ok", "count": 1}],
            "case_id": None,
        }


def _build_client(agent):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.dependency_overrides[get_agent_orchestrator] = lambda: agent
    app.include_router(router, prefix="/api/agent")
    return TestClient(app)


def test_agent_ask_route_forces_verified_only_even_if_client_sends_false():
    agent = _FakeAgent()
    client = _build_client(agent)

    response = client.post(
        "/api/agent/ask",
        json={
            "question": "美国有哪些网络安全认证？",
            "country_code": "US",
            "verified_only": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert agent.payload.verified_only is True


def test_agent_ask_route_rate_limits_authenticated_user(monkeypatch):
    class _TinyLimiter:
        def __init__(self):
            self.calls = 0

        def check(self, key):
            self.calls += 1
            if self.calls > 2:
                return False, "提问次数过多，请稍后再试。"
            return True, None

    monkeypatch.setattr(
        agent_route,
        "AGENT_RATE_LIMITER",
        _TinyLimiter(),
        raising=False,
    )
    client = _build_client(_FakeAgent())

    payload = {
        "question": "美国有哪些网络安全认证？",
        "country_code": "US",
    }
    assert client.post("/api/agent/ask", json=payload).status_code == 200
    assert client.post("/api/agent/ask", json=payload).status_code == 200

    response = client.post("/api/agent/ask", json=payload)

    assert response.status_code == 429
    assert "提问次数过多" in response.json()["detail"]


def test_agent_cases_routes_delegate_to_repository(monkeypatch):
    from database.repository import AgentCaseRepository

    monkeypatch.setattr(
        AgentCaseRepository,
        "list_filtered",
        staticmethod(lambda **kwargs: {"items": [{"id": "case-1", "status": "open"}], "total": 1}),
    )
    captured = {}
    monkeypatch.setattr(
        AgentCaseRepository,
        "apply_decision",
        staticmethod(lambda case_id, decision: captured.update({"case_id": case_id, **decision}) or {"id": case_id, **decision}),
    )

    client = _build_client(_FakeAgent())

    list_response = client.get("/api/agent/cases?status=open")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    decision_response = client.post(
        "/api/agent/cases/case-1/decision",
        json={"status": "triaged", "handler_note": "进入补源队列"},
    )
    assert decision_response.status_code == 200
    assert captured["case_id"] == "case-1"
    assert captured["status"] == "triaged"
