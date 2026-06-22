from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.compliance import router


def test_manual_create_enters_candidate_not_verified(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    captured = {}
    def _fake_create(entry):
        captured["entry"] = entry
        return "rec-1"

    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceRepository.create",
        _fake_create,
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceRepository.set_authenticity_review",
        lambda record_id, **kwargs: captured.setdefault("review", {"record_id": record_id, **kwargs}),
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceRepository.get_by_id",
        lambda record_id: {"id": record_id, **captured["entry"]},
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceIndexRepository.refresh_for_compliance",
        lambda record: captured.setdefault("refreshed", record),
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.ChangeLogRepository.record_change",
        lambda **kwargs: captured.setdefault("change", kwargs),
    )

    client = TestClient(app)
    response = client.post(
        "/api/compliance/",
        json={
            "name": "Example Regulation",
            "entry_type": "regulation",
            "country_code": "EU",
            "mandatory": "mandatory",
        },
    )

    assert response.status_code == 201
    assert captured["entry"]["verified"] is False
    assert captured["entry"]["confidence_score"] == 60
    assert captured["review"]["authenticity_status"] == "candidate"


def test_manual_update_does_not_set_verified(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    captured = {}
    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceRepository.get_by_id",
        lambda record_id: {"id": record_id, "name": "Old", "country_code": "EU", "verified": False},
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceRepository.update",
        lambda record_id, update_data, force=True: captured.setdefault("update_data", update_data) or True,
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceIndexRepository.refresh_for_compliance",
        lambda record: captured.setdefault("refreshed", record),
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.ChangeLogRepository.record_change",
        lambda **kwargs: captured.setdefault("change", kwargs),
    )

    client = TestClient(app)
    response = client.put("/api/compliance/rec-1", json={"name": "New", "verified": True})

    assert response.status_code == 200
    assert "verified" not in captured["update_data"]


def test_compliance_source_download_route(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceRepository.get_by_id",
        lambda record_id: {
            "id": record_id,
            "name": "Cyber Resilience Act",
            "country_code": "EU",
            "official_url": "https://example.com/page",
        },
    )

    captured = {}

    class _FakeService:
        def ingest_record(self, record, requested_by):
            captured["record"] = record
            captured["requested_by"] = requested_by
            return {
                "doc_id": "doc-1",
                "cos_url": "https://cos.example.com/doc.pdf",
                "source_url": "https://example.com/law.pdf",
                "sha256": "b" * 64,
            }

    monkeypatch.setattr("admin.api.routes.compliance.OfficialSourceIngestService", lambda: _FakeService())
    started = {}
    monkeypatch.setattr(
        "admin.api.routes.compliance._parse_and_index_document",
        lambda doc_id, write_to_knowledge=True: started.update({"doc_id": doc_id, "write_to_knowledge": write_to_knowledge}),
    )

    client = TestClient(app)
    response = client.post("/api/compliance/rec-1/source/download")

    assert response.status_code == 200
    payload = response.json()
    assert payload["doc_id"] == "doc-1"
    assert captured["requested_by"] == "tester"
    assert started["doc_id"] == "doc-1"


def test_compliance_manual_source_route_marks_verified_and_triggers_parse(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceRepository.get_by_id",
        lambda record_id: {
            "id": record_id,
            "name": "Cyber Resilience Act",
            "country_code": "EU",
            "data_source": "official_source:EUR-Lex",
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.OfficialSourceRepository.list_all",
        lambda self, **kwargs: [
            {
                "country_code": "EU",
                "name": "EUR-Lex",
                "allowed_domains": ["eur-lex.europa.eu"],
            }
        ],
    )

    captured = {}

    class _FakeService:
        def ingest_manual_source(self, record, official_url, artifact_url=None, requested_by="system"):
            captured["record"] = record
            captured["official_url"] = official_url
            captured["artifact_url"] = artifact_url
            captured["requested_by"] = requested_by
            return {
                "doc_id": "doc-2",
                "cos_url": "https://cos.example.com/cra.pdf",
                "source_url": official_url,
                "sha256": "c" * 64,
                "file_type": "pdf",
            }

    monkeypatch.setattr("admin.api.routes.compliance.OfficialSourceIngestService", lambda: _FakeService())
    reviews = {}
    monkeypatch.setattr(
        "admin.api.routes.compliance.get_authenticity_review_service",
        lambda: type(
            "_FakeReviewService",
            (),
            {
                "register_manual_source": lambda self, record, ingest_result, official_url, evidence_note, checked_by: reviews.update(
                    {
                        "record": record,
                        "official_url": official_url,
                        "evidence_note": evidence_note,
                        "checked_by": checked_by,
                    }
                )
            },
        )(),
    )
    started = {}
    monkeypatch.setattr(
        "admin.api.routes.compliance._parse_and_index_document",
        lambda doc_id, write_to_knowledge=True: started.update({"doc_id": doc_id, "write_to_knowledge": write_to_knowledge}),
    )

    client = TestClient(app)
    response = client.post(
        "/api/compliance/rec-1/manual-source",
        json={
            "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
            "evidence_note": "人工联网确认官方正文页",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["doc_id"] == "doc-2"
    assert payload["authenticity_status"] == "verified"
    assert captured["requested_by"] == "tester"
    assert reviews["checked_by"] == "tester"
    assert started["doc_id"] == "doc-2"
    assert started["write_to_knowledge"] is False


def test_compliance_get_route_returns_review_and_evidence_payload(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    class _FakeCursor:
        executed_sql = ""

        def execute(self, sql, params=None):
            self.executed_sql = sql

        def fetchone(self):
            assert "FROM compliance_index ci" in self.executed_sql
            assert "compliance_knowledge" not in self.executed_sql
            return {
                "id": "rec-1",
                "name": "Cyber Resilience Act",
                "country_code": "EU",
                "country_name": "欧盟",
                "priority": "P1",
                "entry_type": "regulation",
                "mandatory": "mandatory",
                "status": "active",
                "effective_date": None,
                "authenticity_status": "verified",
                "authenticity_risk_score": 0,
                "source_artifact_id": "artifact-1",
                "canonical_requirement_id": "canon-1",
                "review_case_id": "case-1",
                "summary": "officially verified",
            }

    class _CursorContext:
        def __init__(self, cursor):
            self.cursor = cursor

        def __enter__(self):
            return self.cursor

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "admin.api.routes.compliance.get_cursor",
        lambda: _CursorContext(_FakeCursor()),
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.ReviewCaseRepository.get_by_compliance_id",
        lambda record_id: {
            "id": "case-1",
            "current_status": "verified",
            "evidence_note": "confirmed by official source",
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.CanonicalRequirementRepository.get_by_compliance_id",
        lambda record_id: {"id": "canon-1", "verification_status": "verified"},
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.SourceArtifactRepository.list_by_entity",
        lambda record_id: [{"id": "artifact-1", "artifact_url": "https://example.com/law.pdf", "download_status": "downloaded"}],
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.get_authenticity_review_service",
        lambda: type(
            "_FakeReviewService",
            (),
            {
                "get_evidence": lambda self, entity_id: {
                    "entity_id": entity_id,
                    "review_case": {"id": "case-1"},
                    "events": [{"id": 1, "event_type": "manual_source_verified"}],
                    "artifacts": [{"id": "artifact-1"}],
                }
            },
        )(),
    )

    client = TestClient(app)
    response = client.get("/api/compliance/rec-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticity_status"] == "verified"
    assert payload["review_case"]["id"] == "case-1"
    assert payload["source_artifacts"][0]["id"] == "artifact-1"
    assert payload["evidence_events"][0]["event_type"] == "manual_source_verified"


def test_compliance_manual_source_route_rejects_non_whitelisted_domain(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceRepository.get_by_id",
        lambda record_id: {
            "id": record_id,
            "name": "Cyber Resilience Act",
            "country_code": "EU",
            "data_source": "official_source:EUR-Lex",
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.OfficialSourceRepository.list_all",
        lambda self, **kwargs: [
            {
                "country_code": "EU",
                "name": "EUR-Lex",
                "allowed_domains": ["eur-lex.europa.eu"],
            }
        ],
    )

    client = TestClient(app)
    response = client.post(
        "/api/compliance/rec-1/manual-source",
        json={
            "official_url": "https://example.com/fake-law.pdf",
            "evidence_note": "should fail",
        },
    )

    assert response.status_code == 400
    assert "官方域名" in response.json()["detail"]


def test_manual_source_route_allows_record_official_url_domain_fallback(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceRepository.get_by_id",
        lambda record_id: {
            "id": record_id,
            "name": "Cyber Resilience Act",
            "country_code": "EU",
            "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
            "data_source": "manual",
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance.OfficialSourceRepository.list_all",
        lambda self, **kwargs: [],
    )

    class _FakeService:
        def ingest_manual_source(self, record, official_url, artifact_url=None, requested_by="system"):
            return {
                "doc_id": "doc-3",
                "cos_url": "https://cos.example.com/cra.pdf",
                "source_url": official_url,
                "sha256": "d" * 64,
                "file_type": "pdf",
            }

    monkeypatch.setattr("admin.api.routes.compliance.OfficialSourceIngestService", lambda: _FakeService())
    monkeypatch.setattr(
        "admin.api.routes.compliance.get_authenticity_review_service",
        lambda: type(
            "_FakeReviewService",
            (),
            {"register_manual_source": lambda self, *args, **kwargs: None},
        )(),
    )
    monkeypatch.setattr(
        "admin.api.routes.compliance._parse_and_index_document",
        lambda *args, **kwargs: None,
    )

    client = TestClient(app)
    response = client.post(
        "/api/compliance/rec-1/manual-source",
        json={
            "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
            "evidence_note": "record official_url domain fallback",
        },
    )

    assert response.status_code == 200
    assert response.json()["doc_id"] == "doc-3"


def test_compliance_manual_review_route_persists_status_evidence_and_download_state(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    monkeypatch.setattr(
        "admin.api.routes.compliance.ComplianceRepository.get_by_id",
        lambda record_id: {
            "id": record_id,
            "name": "Fake Scheme",
            "country_code": "BG",
            "verified": False,
        },
    )

    monkeypatch.setattr(
        "admin.api.routes.compliance.ReviewCaseRepository.ensure_for_record",
        lambda record: "case-1",
    )
    captured = {}
    monkeypatch.setattr(
        "admin.api.routes.compliance.get_authenticity_review_service",
        lambda: type(
            "_FakeReviewService",
            (),
            {
                "apply_decision": lambda self, case_id, decision, checked_by: captured.update(
                    {"case_id": case_id, "decision": decision, "checked_by": checked_by}
                )
                or {"id": case_id, "current_status": decision["authenticity_status"]}
            },
        )(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/compliance/rec-1/review",
        json={
            "authenticity_status": "quarantined",
            "risk_score": 96,
            "reasons": ["official_domain_mismatch", "official_url_404"],
            "evidence_note": "官方域名与真实机构不一致，目标页 404",
            "source_download_status": "failed",
            "source_download_error": "Target URL returns 404",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticity_status"] == "quarantined"
    assert captured["checked_by"] == "tester"
    assert captured["decision"]["source_download_status"] == "failed"
    assert captured["decision"]["source_download_error"] == "Target URL returns 404"


def test_compliance_verify_route_is_disabled_without_official_evidence(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    client = TestClient(app)
    response = client.post("/api/compliance/rec-1/verify")

    assert response.status_code == 409
    assert "manual-source" in response.json()["detail"]


def test_list_compliance_verified_param_maps_to_verified_only(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    captured = {}
    monkeypatch.setattr(
        "admin.api.routes.compliance.get_compliance_query_service",
        lambda: type(
            "_FakeQueryService",
            (),
            {
                "list_compliance": lambda self, **kwargs: captured.update(kwargs) or {"total": 0, "items": []},
            },
        )(),
    )

    client = TestClient(app)
    response = client.get("/api/compliance/?verified=true")

    assert response.status_code == 200
    assert captured["authenticity_status"] == "verified"
    assert captured["include_suspicious"] is False


def test_list_compliance_defaults_to_verified_only(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    captured = {}
    monkeypatch.setattr(
        "admin.api.routes.compliance.get_compliance_query_service",
        lambda: type(
            "_FakeQueryService",
            (),
            {
                "list_compliance": lambda self, **kwargs: captured.update(kwargs) or {"total": 0, "items": []},
            },
        )(),
    )

    client = TestClient(app)
    response = client.get("/api/compliance/")

    assert response.status_code == 200
    assert captured["authenticity_status"] == "verified"
    assert captured["include_suspicious"] is False


def test_list_compliance_exposes_compliance_id_as_frontend_record_id(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")

    monkeypatch.setattr(
        "admin.api.routes.compliance.get_compliance_query_service",
        lambda: type(
            "_FakeQueryService",
            (),
            {
                "list_compliance": lambda self, **kwargs: {
                    "total": 1,
                    "items": [
                        {
                            "id": "index-row-id",
                            "compliance_id": "record-id",
                            "name": "Cyber Resilience Act",
                            "country_code": "EU",
                            "updated_at": None,
                        }
                    ],
                },
            },
        )(),
    )

    client = TestClient(app)
    response = client.get("/api/compliance/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["id"] == "record-id"
    assert payload["items"][0]["index_id"] == "index-row-id"
