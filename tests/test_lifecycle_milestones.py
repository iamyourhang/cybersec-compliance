from datetime import date
from pathlib import Path

from database.repository import ComplianceLifecycleRepository


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
                "id": "cra-id",
                "name": "Cyber Resilience Act",
                "entry_type": "regulation",
                "country_code": "EU",
                "country_name": "欧盟",
                "priority": 1,
                "mandatory": "mandatory",
                "applicable_products": ["enterprise_router"],
                "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
                "milestone_key": "reporting_obligations_apply",
                "milestone_label_zh": "漏洞与严重事件报告义务开始适用",
                "milestone_label_en": "Reporting obligations apply",
                "milestone_type": "obligation",
                "milestone_date": date(2026, 9, 11),
                "effective_date": date(2026, 9, 11),
                "days_until_milestone": 119,
                "days_until_effective": 119,
                "legal_basis": "Article 71(2); Article 14",
                "obligation_scope": "Article 14 reporting obligations",
                "source_note": "EUR-Lex official text.",
            }
        ]


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_upcoming_milestones_query_uses_verified_lifecycle_table(monkeypatch):
    fake_cursor = _FakeCursor()
    monkeypatch.setattr("database.repository.get_cursor", lambda: _CursorContext(fake_cursor))

    rows = ComplianceLifecycleRepository.get_upcoming_milestones(
        days=180,
        country_code="EU",
        product_code="enterprise_router",
        keyword="CRA",
        limit=50,
    )

    assert rows[0]["effective_date"] == date(2026, 9, 11)
    assert rows[0]["milestone_label_zh"] == "漏洞与严重事件报告义务开始适用"
    assert "compliance_lifecycle_milestones" in fake_cursor.executed_sql
    assert "primary_effective_date" in fake_cursor.executed_sql
    assert "ci.authenticity_status='verified'" in fake_cursor.executed_sql
    assert "milestone_date <= CURRENT_DATE + (%s * INTERVAL '1 day')" in fake_cursor.executed_sql
    assert fake_cursor.executed_params == [180, "EU", "enterprise_router", "%CRA%", 50]


def test_cra_lifecycle_seed_contains_all_article_71_dates():
    migration = Path("database/migrations/V23__compliance_lifecycle_milestones.sql").read_text(encoding="utf-8")

    assert "compliance_lifecycle_milestones" in migration
    assert "2024-12-10" in migration
    assert "2026-06-11" in migration
    assert "2026-09-11" in migration
    assert "2027-12-11" in migration
    assert "Article 71" in migration


class _LifecycleSeedCursor:
    def __init__(self):
        self.calls = []
        self._next = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "SELECT ci.compliance_id::TEXT AS compliance_id" in sql:
            self._next = {"compliance_id": "cra-id"}
        elif "RETURNING milestone_key" in sql:
            self._next = {"milestone_key": params[1]}
        else:
            self._next = None

    def fetchone(self):
        return self._next


def test_key_regulation_seed_upserts_cra_countdown_milestones(monkeypatch):
    fake_cursor = _LifecycleSeedCursor()
    monkeypatch.setattr("database.repository.get_cursor", lambda: _CursorContext(fake_cursor))

    result = ComplianceLifecycleRepository.seed_key_regulation_milestones()

    assert result["cra"]["status"] == "seeded"
    assert result["cra"]["milestones"] == 4
    assert result["cra"]["full_application_date"] == "2027-12-11"
    insert_params = [
        params
        for sql, params in fake_cursor.calls
        if "INSERT INTO compliance_lifecycle_milestones" in sql
    ]
    assert [params[1] for params in insert_params] == [
        "entry_into_force",
        "notified_body_rules_apply",
        "reporting_obligations_apply",
        "full_application",
    ]
    assert [params[5] for params in insert_params] == [
        date(2024, 12, 10),
        date(2026, 6, 11),
        date(2026, 9, 11),
        date(2027, 12, 11),
    ]
