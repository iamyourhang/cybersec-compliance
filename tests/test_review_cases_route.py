from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.review_cases import router as review_cases_router
from admin.api.routes.evidence import router as evidence_router


def _build_client():
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(review_cases_router, prefix="/api/review-cases")
    app.include_router(evidence_router, prefix="/api/evidence")
    return TestClient(app)


def test_review_cases_route_lists_items(monkeypatch):
    client = _build_client()
    monkeypatch.setattr(
        "admin.api.routes.review_cases.get_authenticity_review_service",
        lambda: type(
            "_FakeService",
            (),
            {
                "list_cases": lambda self, **kwargs: {
                    "items": [
                        {
                            "id": "case-1",
                            "record_id": "rec-1",
                            "current_status": "suspicious",
                            "title": "Cyber Resilience Act",
                        }
                    ],
                    "total": 1,
                }
            },
        )(),
    )

    response = client.get("/api/review-cases")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == "case-1"


def test_review_cases_decision_route_persists_decision(monkeypatch):
    client = _build_client()
    captured = {}
    monkeypatch.setattr(
        "admin.api.routes.review_cases.get_authenticity_review_service",
        lambda: type(
            "_FakeService",
            (),
            {
                "apply_decision": lambda self, case_id, decision, checked_by: captured.update(
                    {"case_id": case_id, "decision": decision, "checked_by": checked_by}
                )
                or {
                    "id": case_id,
                    "record_id": "rec-1",
                    "current_status": decision["authenticity_status"],
                }
            },
        )(),
    )

    response = client.post(
        "/api/review-cases/case-1/decision",
        json={
            "authenticity_status": "quarantined",
            "risk_score": 95,
            "reasons": ["official_domain_mismatch"],
            "evidence_note": "wrong domain",
        },
    )

    assert response.status_code == 200
    assert response.json()["current_status"] == "quarantined"
    assert captured["checked_by"] == "tester"


def test_evidence_route_returns_evidence_payload(monkeypatch):
    client = _build_client()
    monkeypatch.setattr(
        "admin.api.routes.evidence.get_authenticity_review_service",
        lambda: type(
            "_FakeService",
            (),
            {
                "get_evidence": lambda self, entity_id: {
                    "entity_id": entity_id,
                    "review_case": {"id": "case-1"},
                    "events": [{"event_type": "manual_review"}],
                    "artifacts": [{"source_url": "https://example.com/law.pdf"}],
                }
            },
        )(),
    )

    response = client.get("/api/evidence/rec-1")

    assert response.status_code == 200
    assert response.json()["entity_id"] == "rec-1"
    assert response.json()["review_case"]["id"] == "case-1"


def test_review_cases_ai_assist_route_returns_summary(monkeypatch):
    client = _build_client()
    monkeypatch.setattr(
        "admin.api.routes.review_cases.get_authenticity_review_service",
        lambda: type(
            "_FakeService",
            (),
            {
                "generate_ai_assist": lambda self, case_id: {
                    "case_id": case_id,
                    "summary": "已确认官方项目存在，但缺少可稳定下载的正文工件。",
                    "evidence_status": "official_program_confirmed",
                    "recommended_actions": ["补官方 PDF", "记录下载失败原因"],
                }
            },
        )(),
    )

    response = client.post("/api/review-cases/case-1/ai-assist")

    assert response.status_code == 200
    assert response.json()["case_id"] == "case-1"
    assert response.json()["recommended_actions"]


def test_review_cases_ai_verify_dry_run_route_returns_suggestions(monkeypatch):
    client = _build_client()
    captured = {}
    monkeypatch.setattr(
        "admin.api.routes.review_cases.get_authenticity_review_service",
        lambda: type(
            "_FakeService",
            (),
            {
                "dry_run_authenticity_verification": lambda self, **kwargs: captured.update(kwargs)
                or {
                    "dry_run": True,
                    "sample_size": 1,
                    "status_counts": {"suspicious": 1},
                    "items": [
                        {
                            "compliance_id": "rec-1",
                            "country_code": "AE",
                            "name": "ETSI EN 303 645",
                            "suggestion": {"suggested_status": "suspicious"},
                        }
                    ],
                }
            },
        )(),
    )

    response = client.post(
        "/api/review-cases/ai-verify-dry-run",
        json={"current_status": "suspicious", "limit": 1, "country_code": "AE"},
    )

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["items"][0]["suggestion"]["suggested_status"] == "suspicious"
    assert captured == {"current_status": "suspicious", "country_code": "AE", "limit": 1}
