from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.documents import router


def _build_client():
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/documents")
    return TestClient(app)


def test_get_document_sections_returns_diagnostics(monkeypatch):
    client = _build_client()

    monkeypatch.setattr(
        "admin.api.routes.documents.DocRepository.get",
        lambda doc_id: {
            "id": doc_id,
            "name": "Cyber Resilience Act",
            "parse_result": {
                "index_diagnostics": {
                    "parsed_count": 18,
                    "filtered_count": 7,
                    "filtered_reason_summary": {
                        "table_of_contents_page": 5,
                        "toc_heading_line": 2,
                    },
                }
            },
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.RegulationSectionRepository.list_by_document",
        lambda doc_id, limit=100: [
            {
                "id": "sec-1",
                "section_index": 0,
                "section_type": "article",
                "section_ref": "Article 1",
                "title": "Scope",
                "section_path": "Chapter I > Article 1",
                "page_from": 3,
                "page_to": 3,
                "content": "This Regulation applies to connected products.",
            }
        ],
    )

    response = client.get("/api/documents/doc-1/sections")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["parsed_count"] == 18
    assert payload["filtered_count"] == 7
    assert payload["filtered_reason_summary"]["table_of_contents_page"] == 5


def test_list_documents_returns_evidence_summary(monkeypatch):
    client = _build_client()

    monkeypatch.setattr(
        "admin.api.routes.documents.DocRepository.list",
        lambda **kwargs: [
            {
                "id": "doc-1",
                "name": "Cyber Resilience Act",
                "country_code": "EU",
                "parse_status": "done",
                "index_status": "ready",
                "compliance_id": "rec-1",
                "chunk_count": 22,
                "spec_requirement_count": 0,
            }
        ],
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.CanonicalRequirementRepository.get_by_document_id",
        lambda doc_id: {
            "id": "canon-1",
            "name": "Cyber Resilience Act",
            "verification_status": "verified",
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.ReviewCaseRepository.get_by_compliance_id",
        lambda compliance_id: {
            "id": "review-1",
            "current_status": "verified",
            "risk_score": 4,
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.SourceArtifactRepository.list_by_entity",
        lambda entity_id: [{"id": "artifact-1"}, {"id": "artifact-2"}],
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.RegulationSpecRequirementRepository.count_by_document",
        lambda doc_id: 3,
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.ComplianceRepository.get_by_id",
        lambda compliance_id: {"id": compliance_id, "authenticity_status": "verified"},
    )

    response = client.get("/api/documents/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["authenticity_status"] == "verified"
    assert item["canonical_requirement_name"] == "Cyber Resilience Act"
    assert item["source_artifact_count"] == 2
    assert item["spec_requirement_count"] == 3
    assert item["is_verified_document"] is True


def test_get_document_returns_evidence_payload(monkeypatch):
    client = _build_client()

    monkeypatch.setattr(
        "admin.api.routes.documents.DocRepository.get",
        lambda doc_id: {
            "id": doc_id,
            "name": "Cyber Resilience Act",
            "country_code": "EU",
            "parse_status": "done",
            "index_status": "ready",
            "compliance_id": "rec-1",
            "chunk_count": 22,
            "spec_requirement_count": 1,
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.CanonicalRequirementRepository.get_by_document_id",
        lambda doc_id: {
            "id": "canon-1",
            "name": "Cyber Resilience Act",
            "verification_status": "verified",
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.ReviewCaseRepository.get_by_compliance_id",
        lambda compliance_id: {
            "id": "review-1",
            "current_status": "verified",
            "risk_score": 2,
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.SourceArtifactRepository.list_by_entity",
        lambda entity_id: [{"id": "artifact-1"}],
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.RegulationSpecRequirementRepository.count_by_document",
        lambda doc_id: 4,
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.ComplianceRepository.get_by_id",
        lambda compliance_id: {"id": compliance_id, "authenticity_status": "verified"},
    )

    response = client.get("/api/documents/doc-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_case_status"] == "verified"
    assert payload["canonical_requirement_id"] == "canon-1"
    assert payload["source_artifact_count"] == 1
    assert payload["spec_requirement_count"] == 4
    assert payload["is_verified_document"] is True


def test_generate_spec_route_returns_stored_count(monkeypatch):
    client = _build_client()

    monkeypatch.setattr(
        "admin.api.routes.documents.DocRepository.get",
        lambda doc_id: {
            "id": doc_id,
            "name": "Cyber Resilience Act",
            "parse_status": "done",
            "compliance_id": "rec-1",
        },
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.ComplianceRepository.get_by_id",
        lambda record_id: {"id": record_id, "authenticity_status": "verified"},
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.CanonicalRequirementRepository.get_by_document_id",
        lambda document_id: None,
    )

    captured = {}
    monkeypatch.setattr(
        "admin.api.routes.documents._generate_spec_document",
        lambda doc_id, applicable_products: captured.update(
            {"doc_id": doc_id, "applicable_products": applicable_products}
        ),
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.DocRepository.reset_spec_progress",
        lambda doc_id, msg="等待生成规格": captured.update({"reset_doc_id": doc_id, "reset_msg": msg}),
    )
    monkeypatch.setattr(
        "admin.api.routes.documents.DocRepository.set_spec_progress",
        lambda doc_id, progress, msg: captured.update(
            {"progress_doc_id": doc_id, "progress": progress, "progress_msg": msg}
        ),
    )

    response = client.post("/api/documents/doc-1/generate-spec", json={"applicable_products": None})

    assert response.status_code == 200
    payload = response.json()
    assert payload["doc_id"] == "doc-1"
    assert payload["spec_progress"] == 3
    assert captured["doc_id"] == "doc-1"
    assert captured["progress"] == 3


def test_generate_spec_route_rejects_running_job(monkeypatch):
    client = _build_client()

    monkeypatch.setattr(
        "admin.api.routes.documents.DocRepository.get",
        lambda doc_id: {
            "id": doc_id,
            "name": "Cyber Resilience Act",
            "parse_status": "done",
            "compliance_id": "rec-1",
            "spec_progress": 42,
        },
    )

    response = client.post("/api/documents/doc-1/generate-spec", json={"applicable_products": None})

    assert response.status_code == 409
    assert response.json()["detail"] == "规格生成任务正在进行中"
