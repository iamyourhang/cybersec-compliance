from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.official_sources import (
    get_official_source_pipeline,
    get_official_source_repository,
    router,
)


class _FakeRepo:
    def list_all(self, country_priorities=None, enabled_only=False):
        return [
            {
                "id": "src-1",
                "name": "EUR-Lex",
                "country_code": "EU",
                "source_type": "html_list",
                "enabled": True,
                "priority": 1,
                "country_priority": "P1",
            }
        ]

    def list_history(self, source_id, limit=20):
        return [{"id": 1, "status": "success"}]


class _FakePipeline:
    def sync_source(self, source_id):
        return {"source_id": source_id, "discovered_count": 2, "candidate_count": 1}


def _build_client():
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.dependency_overrides[get_official_source_repository] = lambda: _FakeRepo()
    app.dependency_overrides[get_official_source_pipeline] = lambda: _FakePipeline()
    app.include_router(router, prefix="/api/official-sources")
    return TestClient(app)


def test_list_official_sources():
    client = _build_client()

    response = client.get("/api/official-sources/")

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "EUR-Lex"


def test_sync_official_source():
    client = _build_client()

    response = client.post("/api/official-sources/src-1/sync")

    assert response.status_code == 200
    assert response.json()["candidate_count"] == 1


def test_sync_official_source_returns_502_on_fetch_failure():
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.dependency_overrides[get_official_source_repository] = lambda: _FakeRepo()

    class _BrokenPipeline:
        def sync_source(self, source_id):
            raise ValueError("抓取官方源失败: timed out")

    app.dependency_overrides[get_official_source_pipeline] = lambda: _BrokenPipeline()
    app.include_router(router, prefix="/api/official-sources")
    client = TestClient(app)

    response = client.post("/api/official-sources/src-1/sync")

    assert response.status_code == 502
    assert "timed out" in response.json()["detail"]
