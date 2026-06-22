from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.rag import AskRequest, router


class _StubRAGService:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def ask(self, request: AskRequest):
        self.calls.append(request)
        return self.response


def _build_client(service):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.state.rag_service = service
    app.include_router(router, prefix="/api/rag")
    return TestClient(app)


def test_rag_route_returns_grounded_answer_shape():
    service = _StubRAGService(
        {
            "status": "answered",
            "answer": "根据原文，设备必须提供默认安全配置。",
            "citations": [
                {
                    "document_id": "doc-1",
                    "document_name": "Cyber Resilience Act",
                    "page_from": 12,
                    "page_to": 13,
                    "clause_ref": "Article 10",
                    "excerpt": "secure by default configurations",
                    "country_code": "EU",
                }
            ],
            "related_records": [
                {
                    "id": "rec-1",
                    "name": "Cyber Resilience Act",
                    "entry_type": "regulation",
                    "country_code": "EU",
                }
            ],
            "trace": {
                "grounding_mode": "verified_local_corpus",
                "verified_only": True,
                "retrieval_counts": {"merged_hits": 2},
            },
        }
    )

    client = _build_client(service)
    response = client.post(
        "/api/rag/ask",
        json={
            "question": "CRA 对防火墙的默认安全要求有哪些？",
            "country_code": "EU",
            "product_code": "firewall_utm",
            "document_id": None,
            "top_k": 6,
            "verified_only": True,
            "history": [{"role": "user", "content": "先看 CRA"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "answered"
    assert payload["citations"][0]["document_name"] == "Cyber Resilience Act"
    assert service.calls[0].product_code == "firewall_utm"
    assert service.calls[0].verified_only is True
    assert len(service.calls[0].history) == 1
    assert payload["trace"]["grounding_mode"] == "verified_local_corpus"


def test_rag_route_returns_insufficient_evidence_shape():
    service = _StubRAGService(
        {
            "status": "insufficient_evidence",
            "answer": "现有原文证据不足以确认该结论。",
            "citations": [],
            "related_records": [],
            "trace": {"grounding_mode": "verified_local_corpus", "verified_only": True},
        }
    )

    client = _build_client(service)
    response = client.post(
        "/api/rag/ask",
        json={
            "question": "某法规是否要求芯片级加密？",
            "country_code": "EU",
            "product_code": None,
            "document_id": None,
            "top_k": 6,
            "verified_only": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_evidence"


def test_rag_route_forces_verified_local_corpus():
    service = _StubRAGService(
        {
            "status": "insufficient_evidence",
            "answer": "现有原文证据不足以确认该结论。",
            "citations": [],
            "related_records": [],
            "trace": {"grounding_mode": "verified_local_corpus", "verified_only": True},
        }
    )

    client = _build_client(service)
    response = client.post(
        "/api/rag/ask",
        json={
            "question": "CRA 对默认安全配置有哪些要求？",
            "country_code": "EU",
            "verified_only": False,
        },
    )

    assert response.status_code == 200
    assert service.calls[0].verified_only is True
