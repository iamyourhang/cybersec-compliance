from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.discovery import get_ai_discovery_service, get_candidate_validation_service, router


class _FakeDiscoveryService:
    def __init__(self):
        self.calls = []

    def run(self, priorities=None, limit_countries=20, queries_per_country=3, validation_mode="ai"):
        self.calls.append(
            {
                "priorities": priorities,
                "limit_countries": limit_countries,
                "queries_per_country": queries_per_country,
                "validation_mode": validation_mode,
            }
        )
        return {
            "run_id": "run-1",
            "countries_count": 2,
            "queries_count": 6,
            "candidate_count": 3,
            "accepted_count": 2,
            "rejected_count": 1,
            "status": "success",
        }


class _FakeRepository:
    def list_runs(self, limit=20, offset=0):
        return [
            {
                "id": "run-1",
                "status": "success",
                "candidate_count": 3,
                "started_at": "2026-05-16 09:00",
            }
        ]

    def list_candidates(self, limit=50, offset=0, country_code=None):
        return [
            {
                "id": "src-1",
                "country_code": country_code or "SG",
                "title": "Cybersecurity Labelling Scheme for IoT",
                "discovery_method": "ai_weekly_discovery",
            }
        ]


class _FakeValidationService:
    def __init__(self):
        self.calls = []

    def validate(self, source_record_id, **kwargs):
        self.calls.append({"source_record_id": source_record_id, **kwargs})
        return {
            "source_record_id": source_record_id,
            "source_status": "candidate",
            "validation_stage": {
                "mode": kwargs["mode"],
                "status": kwargs.get("decision") or "accepted",
            },
        }


def _client(fake_service, fake_repository, fake_validation=None):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.dependency_overrides[get_ai_discovery_service] = lambda: fake_service
    if fake_validation:
        app.dependency_overrides[get_candidate_validation_service] = lambda: fake_validation
    app.state.ai_discovery_repository = fake_repository
    app.include_router(router, prefix="/api/discovery")
    return TestClient(app)


def test_discovery_run_endpoint_triggers_service():
    fake_service = _FakeDiscoveryService()
    client = _client(fake_service, _FakeRepository())

    response = client.post("/api/discovery/run", json={"priorities": ["P0", "P1"], "limit_countries": 2})

    assert response.status_code == 200
    assert response.json()["accepted_count"] == 2
    assert fake_service.calls == [
        {
            "priorities": ["P0", "P1"],
            "limit_countries": 2,
            "queries_per_country": 3,
            "validation_mode": "ai",
        }
    ]


def test_discovery_list_endpoints_return_runs_and_candidates():
    client = _client(_FakeDiscoveryService(), _FakeRepository())

    runs = client.get("/api/discovery/runs").json()
    candidates = client.get("/api/discovery/candidates?country_code=SG").json()

    assert runs["items"][0]["id"] == "run-1"
    assert candidates["items"][0]["discovery_method"] == "ai_weekly_discovery"


def test_discovery_candidate_manual_validation_endpoint():
    fake_validation = _FakeValidationService()
    client = _client(_FakeDiscoveryService(), _FakeRepository(), fake_validation)

    response = client.post(
        "/api/discovery/candidates/src-1/validate",
        json={
            "mode": "manual",
            "decision": "accepted",
            "reasons": ["official_domain_confirmed"],
            "evidence_note": "人工确认官方链接和产品网络安全相关性。",
        },
    )

    assert response.status_code == 200
    assert response.json()["source_status"] == "candidate"
    assert fake_validation.calls[0]["source_record_id"] == "src-1"
    assert fake_validation.calls[0]["checked_by"] == "tester"
