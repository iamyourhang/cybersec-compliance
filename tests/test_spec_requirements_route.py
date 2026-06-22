from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.spec_requirements import router


def test_list_spec_requirements_filters_and_returns_items(monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/spec-requirements")

    captured = {}

    monkeypatch.setattr(
        "admin.api.routes.spec_requirements.RegulationSpecRequirementRepository.list_filtered",
        lambda **kwargs: captured.update(kwargs) or [
            {
                "id": "req-1",
                "document_id": "doc-1",
                "country_code": "EU",
                "req_id": "AUTH-001",
                "title_zh": "默认密码修改",
                "priority": "P1",
                "regulation_clause": "Article 10",
                "applicable_products": ["home_router"],
            }
        ],
    )

    client = TestClient(app)
    response = client.get(
        "/api/spec-requirements",
        params={
            "document_id": "doc-1",
            "country_code": "EU",
            "product_code": "home_router",
            "priority": "P1",
            "regulation_clause": "Article 10",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["req_id"] == "AUTH-001"
    assert captured["document_id"] == "doc-1"
    assert captured["product_code"] == "home_router"
