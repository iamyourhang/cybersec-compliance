from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.routes.public import _normalize_country, router


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def _disable_translation_db_lookup(monkeypatch):
    monkeypatch.setattr(
        "admin.api.routes.public.list_translations_for_entities",
        lambda entity_type, entity_ids: {},
    )


def test_public_country_normalization_uses_china_taiwan_display_name():
    row = _normalize_country({"code": "TW", "name_zh": "台湾", "name_en": "Taiwan"})

    assert row["name_zh"] == "中国台湾"
    assert row["name_en"] == "Taiwan, China"
    assert row["jurisdiction_type"] == "special_region"


class _RecentChangesCursor:
    def __init__(self):
        self.executed_sql = ""

    def execute(self, sql, params=None):
        self.executed_sql = sql

    def fetchall(self):
        assert "compliance_knowledge" not in self.executed_sql
        if "compliance_index" not in self.executed_sql or "UNION ALL" not in self.executed_sql:
            return []
        return [
            {
                "change_type": "created",
                "changed_at": datetime(2026, 5, 9, 3, 21, tzinfo=timezone.utc),
                "id": "record-1",
                "name": "Afghanistan MCIT Draft Cyber Security Plan 2015",
                "country_code": "AF",
                "country_name": "阿富汗",
            }
        ]


class _CountriesCursor:
    def __init__(self):
        self.executed_sql = ""

    def execute(self, sql, params=None):
        self.executed_sql = sql
        assert "c.jurisdiction_type" in sql

    def fetchall(self):
        assert "country_source_coverage" in self.executed_sql
        assert "LEFT JOIN country_source_coverage" in self.executed_sql
        return [
            {
                "code": "KN",
                "name_zh": "圣基茨和尼维斯",
                "name_en": "Saint Kitts and Nevis",
                "region": "美洲",
                "jurisdiction_type": "country",
                "priority": "P3",
                "coverage_status": "official_sources_seeded",
                "product_coverage_status": "pending_source_research",
                "official_source_count": 1,
                "source_record_count": 0,
                "total": 0,
                "verified_record_count": 0,
                "inherited_verified_count": 2,
                "display_verified_count": 2,
                "product_verified_count": 0,
                "general_verified_count": 0,
                "suspicious_record_count": 0,
                "quarantined_record_count": 0,
                "review_note": "official source seeded",
                "next_action": "运行官方源同步",
                "last_checked_at": datetime(2026, 5, 9, 3, 21, tzinfo=timezone.utc),
                "mandatory_cnt": 0,
                "cert_cnt": 0,
            }
        ]


class _ItemDetailCursor:
    def __init__(self):
        self.executed_sql = ""

    def execute(self, sql, params=None):
        self.executed_sql = sql

    def fetchone(self):
        assert "ci.authenticity_status='verified'" in self.executed_sql
        assert "COALESCE(ready_doc.id, ci.document_id) AS document_id" in self.executed_sql
        assert "replacement" not in self.executed_sql
        assert "regulation_documents d" in self.executed_sql
        assert "compliance_knowledge" not in self.executed_sql
        return {
            "id": "record-1",
            "name": "Cybersecurity Act",
            "country_code": "GB",
            "country_name": "英国",
            "country_name_en": "United Kingdom",
            "region": "欧洲",
            "entry_type": "regulation",
            "mandatory": "mandatory",
            "status": "active",
            "issuing_body": "Official Publisher",
            "official_url": "https://www.legislation.gov.uk/",
            "applicable_products": ["iot"],
            "effective_date": datetime(2026, 4, 29, tzinfo=timezone.utc).date(),
            "published_date": None,
            "summary": "Verified summary",
            "document_id": "doc-1",
            "source_artifact_id": "artifact-1",
            "review_case_id": "review-1",
            "updated_at": datetime(2026, 5, 9, 3, 21, tzinfo=timezone.utc),
            "evidence_note": "Official PDF verified",
            "reasons": [],
            "checked_at": datetime(2026, 5, 9, 3, 21, tzinfo=timezone.utc),
            "source_artifact_url": "https://www.legislation.gov.uk/",
            "artifact_sha256": "abc",
        }

    def fetchall(self):
        if "compliance_lifecycle_milestones" in self.executed_sql:
            return [
                {
                    "milestone_key": "reporting_obligations_apply",
                    "milestone_type": "obligation",
                    "milestone_label_zh": "漏洞与严重事件报告义务开始适用",
                    "milestone_label_en": "Reporting obligations apply",
                    "milestone_date": datetime(2026, 9, 11, tzinfo=timezone.utc).date(),
                    "obligation_scope": "Article 14 reporting obligations",
                    "legal_basis": "Article 71(2); Article 14",
                    "source_note": "Official lifecycle node.",
                    "priority": 30,
                }
            ]
        return []


class _CountryDetailCursor:
    def __init__(self):
        self.executed_sql = ""
        self.calls = 0

    def execute(self, sql, params=None):
        self.executed_sql = sql
        if "FROM compliance_index ci" in sql and "COALESCE(ready_doc.id, ci.document_id) AS document_id" in sql:
            assert "FROM compliance_index ci" in sql
            assert "COALESCE(ready_doc.id, ci.document_id) AS document_id" in sql
            assert "regulation_documents d" in sql
            assert "jurisdiction_inheritance" in sql

    def fetchone(self):
        self.calls += 1
        if self.calls == 1:
            return {
                "code": "EU",
                "name_zh": "欧盟",
                "name_en": "European Union",
                "region": "欧洲",
                "jurisdiction_type": "regional_bloc",
            }
        if self.calls == 2:
            return {
                "country_code": "KN",
                "coverage_status": "official_sources_seeded",
                "product_coverage_status": "pending_source_research",
                "official_source_count": 1,
                "source_record_count": 0,
                "verified_record_count": 0,
                "product_verified_count": 0,
                "general_verified_count": 0,
                "review_note": "official source seeded",
                "next_action": "download artifact",
                "last_checked_at": None,
                "updated_at": None,
            }
        return None

    def fetchall(self):
        if "FROM compliance_index ci" in self.executed_sql:
            return [
                {
                    "id": "record-1",
                    "name": "Electronic Crimes Act",
                    "entry_type": "regulation",
                    "mandatory": "mandatory",
                    "effective_date": None,
                    "published_date": None,
                    "issuing_body": "Law Commission",
                    "official_url": "https://lawcommission.gov.kn/",
                    "status": "active",
                    "summary": "summary",
                    "applicable_products": [],
                    "document_id": None,
                    "source_artifact_id": None,
                    "source_record_id": None,
                    "updated_at": None,
                    "source_jurisdiction_code": "KN",
                    "source_jurisdiction_name": "圣基茨和尼维斯",
                    "scope_origin": "local",
                    "inherited_from_code": None,
                    "inheritance_reason": None,
                },
                {
                    "id": "record-eu",
                    "name": "EU Cyber Resilience Act",
                    "entry_type": "regulation",
                    "regime_category": "product_regime",
                    "mandatory": "mandatory",
                    "effective_date": None,
                    "published_date": None,
                    "issuing_body": "European Parliament and Council",
                    "official_url": "https://eur-lex.europa.eu/",
                    "status": "active",
                    "summary": "EU product cybersecurity regulation",
                    "applicable_products": ["switch"],
                    "document_id": "doc-eu",
                    "source_artifact_id": None,
                    "source_record_id": None,
                    "updated_at": None,
                    "source_jurisdiction_code": "EU",
                    "source_jurisdiction_name": "欧盟",
                    "scope_origin": "inherited",
                    "inherited_from_code": "EU",
                    "inheritance_reason": "EU member state",
                }
            ]
        if "FROM official_sources" in self.executed_sql:
            return [
                {
                    "id": "source-1",
                    "name": "Saint Kitts and Nevis Law Commission Electronic Crimes Act",
                    "source_type": "pdf_index",
                    "list_url": "https://lawcommission.gov.kn/",
                    "base_url": "https://lawcommission.gov.kn",
                    "allowed_domains": ["lawcommission.gov.kn"],
                    "entry_type_scope": ["regulation"],
                    "priority": 215,
                    "last_checked_at": None,
                    "last_success_at": None,
                    "last_error": None,
                    "parser_config": {"official_evidence_url": "https://lawcommission.gov.kn/", "evidence_note": "official source"},
                }
            ]
        return []


def test_public_recent_changes_includes_verified_records_without_legacy_change_log(monkeypatch):
    fake_cursor = _RecentChangesCursor()
    monkeypatch.setattr("admin.api.routes.public.get_cursor", lambda: _CursorContext(fake_cursor))
    app = FastAPI()
    app.include_router(router, prefix="/api/public")
    client = TestClient(app)

    response = client.get("/api/public/recent-changes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == [
        {
            "change_type": "created",
            "changed_at": "2026-05-09 03:21",
            "id": "record-1",
            "name": "Afghanistan MCIT Draft Cyber Security Plan 2015",
            "country_code": "AF",
            "country_name": "阿富汗",
        }
    ]


def test_public_countries_are_backed_by_country_source_coverage(monkeypatch):
    fake_cursor = _CountriesCursor()
    monkeypatch.setattr("admin.api.routes.public.get_cursor", lambda: _CursorContext(fake_cursor))
    app = FastAPI()
    app.include_router(router, prefix="/api/public")
    client = TestClient(app)

    response = client.get("/api/public/countries")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["code"] == "KN"
    assert payload[0]["jurisdiction_type"] == "country"
    assert payload[0]["coverage_status"] == "official_sources_seeded"
    assert payload[0]["official_source_count"] == 1
    assert payload[0]["total"] == 0
    assert payload[0]["inherited_verified_count"] == 2
    assert payload[0]["display_verified_count"] == 2
    assert payload[0]["last_checked_at"] == "2026-05-09 03:21"
    assert "suspicious_record_count" not in payload[0]
    assert "quarantined_record_count" not in payload[0]
    assert "source_record_count" not in payload[0]


def test_public_item_detail_uses_verified_read_model_id(monkeypatch):
    fake_cursor = _ItemDetailCursor()
    monkeypatch.setattr("admin.api.routes.public.get_cursor", lambda: _CursorContext(fake_cursor))
    app = FastAPI()
    app.include_router(router, prefix="/api/public")
    client = TestClient(app)

    response = client.get("/api/public/item/record-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "record-1"
    assert payload["document_id"] == "doc-1"
    assert payload["evidence_note"] == "Official PDF verified"
    assert payload["lifecycle_milestones"][0]["milestone_date"] == "2026-09-11"
    assert payload["lifecycle_milestones"][0]["milestone_label_zh"] == "漏洞与严重事件报告义务开始适用"
    assert "technical_standards" not in payload


def test_public_country_detail_returns_verified_items_and_official_sources(monkeypatch):
    fake_cursor = _CountryDetailCursor()
    monkeypatch.setattr("admin.api.routes.public.get_cursor", lambda: _CursorContext(fake_cursor))
    app = FastAPI()
    app.include_router(router, prefix="/api/public")
    client = TestClient(app)

    response = client.get("/api/public/country/KN")

    assert response.status_code == 200
    payload = response.json()
    assert payload["country"]["jurisdiction_type"] == "regional_bloc"
    assert payload["coverage"]["coverage_status"] == "official_sources_seeded"
    assert payload["items"][0]["id"] == "record-1"
    assert payload["items"][1]["id"] == "record-eu"
    assert payload["items"][1]["scope_origin"] == "inherited"
    assert payload["items"][1]["inherited_from_code"] == "EU"
    assert payload["official_sources"][0]["official_evidence_url"] == "https://lawcommission.gov.kn/"


def test_public_country_detail_attaches_additive_translations(monkeypatch):
    fake_cursor = _CountryDetailCursor()

    def fake_translations(entity_type, entity_ids):
        if entity_type == "compliance_index":
            return {("record-1", "name"): "《电子犯罪法》", ("record-1", "summary"): "中文摘要"}
        if entity_type == "official_sources":
            return {("source-1", "name"): "圣基茨和尼维斯法律委员会电子犯罪法来源"}
        if entity_type == "country_source_coverage":
            return {("KN", "next_action"): "下载官方工件"}
        return {}

    monkeypatch.setattr("admin.api.routes.public.get_cursor", lambda: _CursorContext(fake_cursor))
    monkeypatch.setattr("admin.api.routes.public.list_translations_for_entities", fake_translations)
    app = FastAPI()
    app.include_router(router, prefix="/api/public")
    client = TestClient(app)

    response = client.get("/api/public/country/KN")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["name"] == "Electronic Crimes Act"
    assert payload["items"][0]["name_zh"] == "《电子犯罪法》"
    assert payload["items"][0]["summary_zh"] == "中文摘要"
    assert payload["coverage"]["next_action_zh"] == "下载官方工件"
    assert payload["official_sources"][0]["name_zh"] == "圣基茨和尼维斯法律委员会电子犯罪法来源"
