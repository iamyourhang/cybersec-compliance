from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.compliance import router


class _FakeCursor:
    def __init__(self):
        self.executed_sql = ""
        self.executed_params = None

    def execute(self, sql, params=None):
        self.executed_sql = sql
        self.executed_params = params or []

    def fetchall(self):
        return []


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_export_excel_defaults_to_verified_only(monkeypatch):
    fake_cursor = _FakeCursor()
    monkeypatch.setattr(
        "admin.api.routes.compliance.get_cursor",
        lambda: _CursorContext(fake_cursor),
    )

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/compliance")
    client = TestClient(app)

    response = client.get("/api/compliance/export/excel")

    assert response.status_code == 200
    assert "FROM compliance_index ci" in fake_cursor.executed_sql
    assert "ci.authenticity_status = 'verified'" in fake_cursor.executed_sql
    assert "JOIN compliance_knowledge" not in fake_cursor.executed_sql
    assert "ck.verified=TRUE" not in fake_cursor.executed_sql
    assert "<> 'quarantined'" not in fake_cursor.executed_sql
