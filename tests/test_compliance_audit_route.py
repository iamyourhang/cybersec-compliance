from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.compliance import router


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return {"cnt": len(self.rows)}


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def _build_client(fake_cursor, monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    monkeypatch.setattr("admin.api.routes.compliance.get_cursor", lambda: _CursorContext(fake_cursor))
    app.include_router(router, prefix="/api/compliance")
    return TestClient(app)


def test_compliance_audit_route_returns_ranked_suspicious_items(monkeypatch):
    fake_cursor = _FakeCursor(
        [
            {
                "id": "row-1",
                "name": "National Cybersecurity Certification Scheme for Network Equipment",
                "country_code": "SD",
                "entry_type": "certification",
                "issuing_body": "Some Authority",
                "official_url": None,
                "verified": False,
                "confidence_score": 60,
                "data_source": "volcengine_primary/doubao-seed-2-0-pro-260215",
                "status": "active",
            }
        ]
    )
    client = _build_client(fake_cursor, monkeypatch)

    response = client.get("/api/compliance/audit/suspicious")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["risk_score"] >= 70
    assert "template_like_name" in payload["items"][0]["reasons"]


def test_pending_review_route_uses_authenticity_queue(monkeypatch):
    fake_cursor = _FakeCursor(
        [
            {
                "id": "row-1",
                "name": "Cyber Resilience Act",
                "country_code": "EU",
                "country_name": "欧盟",
                "authenticity_status": "candidate",
                "source_download_status": "pending",
                "verified": False,
                "confidence_score": 60,
                "data_source": "official_source:EUR-Lex",
                "status": "active",
            }
        ]
    )
    client = _build_client(fake_cursor, monkeypatch)

    response = client.get("/api/compliance/review/pending?limit=20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["authenticity_status"] == "candidate"
    executed_sql, executed_params = fake_cursor.executed[0]
    assert "authenticity_status" in executed_sql
    assert executed_params == (20,)


def test_pending_review_route_supports_official_url_missing_bucket(monkeypatch):
    fake_cursor = _FakeCursor([])
    client = _build_client(fake_cursor, monkeypatch)

    response = client.get("/api/compliance/review/pending?limit=20&review_bucket=official_url_missing")

    assert response.status_code == 200
    executed_sql, executed_params = fake_cursor.executed[0]
    assert "ci.official_url IS NULL" in executed_sql
    assert executed_params == (20,)


def test_pending_review_route_supports_domain_mismatch_bucket(monkeypatch):
    fake_cursor = _FakeCursor([])
    client = _build_client(fake_cursor, monkeypatch)

    response = client.get("/api/compliance/review/pending?limit=20&review_bucket=domain_mismatch")

    assert response.status_code == 200
    executed_sql, executed_params = fake_cursor.executed[0]
    assert "authenticity_reasons" in executed_sql
    assert "official_domain_mismatch" in executed_sql
    assert executed_params == (20,)
