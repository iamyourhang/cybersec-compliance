from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.dashboard import router


class _FakeCursor:
    def __init__(self):
        self.executed_sql = ""
        self.executed_params = None

    def execute(self, sql, params=None):
        self.executed_sql = sql
        self.executed_params = params or []

    def fetchall(self):
        return [
            {
                "id": "row-1",
                "name": "Cyber Resilience Act",
                "country_code": "EU",
                "country_name": "欧盟",
                "priority": 1,
                "entry_type": "regulation",
                "mandatory": "mandatory",
                "milestone_key": "reporting_obligations_apply",
                "milestone_label_zh": "漏洞与严重事件报告义务开始适用",
                "milestone_label_en": "Reporting obligations apply",
                "milestone_type": "obligation",
                "effective_date": date(2026, 9, 11),
                "milestone_date": date(2026, 9, 11),
                "days_until_effective": 140,
                "applicable_products": ["router"],
                "official_url": "https://eur-lex.europa.eu/",
                "summary": "Official verified record.",
            }
        ]


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def _client(fake_cursor, monkeypatch):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    monkeypatch.setattr("admin.api.routes.dashboard.get_cursor", lambda: _CursorContext(fake_cursor))
    app.include_router(router, prefix="/api/dashboard")
    return TestClient(app)


def test_upcoming_supports_verified_only_day_window_and_filters(monkeypatch):
    fake_cursor = _FakeCursor()
    captured = {}

    def _fake_upcoming(**kwargs):
        captured.update(kwargs)
        return fake_cursor.fetchall()

    monkeypatch.setattr(
        "admin.api.routes.dashboard.ComplianceLifecycleRepository.get_upcoming_milestones",
        _fake_upcoming,
    )
    client = _client(fake_cursor, monkeypatch)

    response = client.get(
        "/api/dashboard/upcoming",
        params={
            "days": 180,
            "country_code": "EU",
            "entry_type": "regulation",
            "mandatory": "mandatory",
            "product_code": "router",
            "keyword": "CRA",
            "limit": 50,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 180
    assert payload["total"] == 1
    assert payload["items"][0]["effective_date"] == "2026-09-11"
    assert payload["items"][0]["milestone_date"] == "2026-09-11"
    assert payload["items"][0]["milestone_label_zh"] == "漏洞与严重事件报告义务开始适用"
    assert captured == {
        "days": 180,
        "country_code": "EU",
        "product_code": "router",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "keyword": "CRA",
        "limit": 50,
    }


def test_upcoming_rejects_unsupported_day_window(monkeypatch):
    fake_cursor = _FakeCursor()
    client = _client(fake_cursor, monkeypatch)

    response = client.get("/api/dashboard/upcoming?days=45")

    assert response.status_code == 400
    assert "30/90/180/360" in response.json()["detail"]


class _WorkflowCursor:
    def __init__(self):
        self.sqls = []

    def execute(self, sql, params=None):
        self.sqls.append(sql)
        self.current_sql = sql

    def fetchone(self):
        sql = self.current_sql
        if "FROM source_records" in sql:
            return {"cnt": 12}
        if "FROM source_artifacts" in sql and "download_status='downloaded'" in sql:
            return {"cnt": 9}
        if "FROM source_artifacts" in sql and "download_status='failed'" in sql:
            return {"cnt": 2}
        if "FROM review_cases" in sql and "current_status='verified'" in sql:
            return {"cnt": 7}
        if "FROM review_cases" in sql and "current_status='suspicious'" in sql:
            return {"cnt": 3}
        if "FROM review_cases" in sql and "current_status='quarantined'" in sql:
            return {"cnt": 1}
        if "FROM compliance_index" in sql and "effective_date BETWEEN" in sql:
            return {"cnt": 4}
        if "FROM compliance_index" in sql:
            return {"cnt": 7}
        if "FROM regulation_documents" in sql and "index_status='ready'" in sql:
            return {"cnt": 5}
        if "FROM regulation_documents" in sql and "parse_status='done'" in sql:
            return {"cnt": 6}
        if "FROM regulation_documents" in sql and "spec_requirement_count" in sql:
            return {"cnt": 2}
        if "FROM regulation_document_chunks" in sql:
            return {"cnt": 300}
        if "FROM regulation_spec_requirements" in sql:
            return {"cnt": 24}
        if "FROM change_log" in sql:
            return {"cnt": 8}
        if "FROM report_records" in sql:
            return {"cnt": 1}
        return {"cnt": 0}


def test_workflow_endpoint_exposes_evidence_driven_product_stages(monkeypatch):
    fake_cursor = _WorkflowCursor()
    monkeypatch.setattr(
        "admin.api.routes.dashboard.ComplianceLifecycleRepository.get_upcoming_milestones",
        lambda days, limit: [{"id": f"upcoming-{i}"} for i in range(4)],
    )
    client = _client(fake_cursor, monkeypatch)

    response = client.get("/api/dashboard/workflow")

    assert response.status_code == 200
    payload = response.json()
    assert "官方证据闭环" in payload["principle"]
    assert [stage["key"] for stage in payload["stages"]] == [
        "source_collection",
        "evidence_review",
        "knowledge_deposit",
        "spec_output",
        "query_use",
        "alerts_weekly",
    ]
    assert payload["stages"][0]["title"] == "信息采集"
    assert payload["stages"][2]["primary_label"] == "正式条目"
    assert payload["stages"][3]["primary_value"] == 24
    assert payload["stages"][5]["metrics"][0] == {"label": "待审变更", "value": 8}
    assert any("regulation_document_chunks" in sql for sql in fake_cursor.sqls)
