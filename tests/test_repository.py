from database import repository as repository_module
import json

from database.repository import ComplianceRepository, SourceRecordRepository, _normalize_jsonb
from database.repository import (
    _ensure_compliance_create_review_gate,
    _ensure_verified_review_gate,
)


class _FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchall(self):
        return [
            {
                "id": "fd94580f-5c8b-4d84-9bf7-181650cb4a6b",
                "name": "Cyber Resilience Act",
                "entry_type": "regulation",
                "country_code": "EU",
            }
        ]


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_list_by_ids_casts_array_to_uuid(monkeypatch):
    fake_cursor = _FakeCursor()
    monkeypatch.setattr(
        repository_module,
        "get_cursor",
        lambda: _CursorContext(fake_cursor),
    )

    rows = ComplianceRepository.list_by_ids(
        ["fd94580f-5c8b-4d84-9bf7-181650cb4a6b"]
    )

    sql, params = fake_cursor.executed[0]
    assert "ANY(%s::uuid[])" in sql
    assert params == (["fd94580f-5c8b-4d84-9bf7-181650cb4a6b"],)
    assert rows[0]["country_code"] == "EU"


def test_list_pending_source_artifacts_escapes_like_percent(monkeypatch):
    fake_cursor = _FakeCursor()
    monkeypatch.setattr(
        repository_module,
        "get_cursor",
        lambda: _CursorContext(fake_cursor),
    )

    ComplianceRepository.list_pending_source_artifacts(limit=20)

    sql, params = fake_cursor.executed[0]
    assert "data_source LIKE 'official_source:%%'" in sql
    assert params == (20,)


def test_normalize_jsonb_serializes_list_values():
    payload = {"authenticity_reasons": ["requires_review_before_verified"]}

    _normalize_jsonb(payload, ["authenticity_reasons"])

    assert json.loads(payload["authenticity_reasons"]) == ["requires_review_before_verified"]


def test_list_downloaded_source_candidates_escapes_like_percent(monkeypatch):
    fake_cursor = _FakeCursor()
    monkeypatch.setattr(
        repository_module,
        "get_cursor",
        lambda: _CursorContext(fake_cursor),
    )

    ComplianceRepository.list_downloaded_source_candidates(limit=50)

    sql, params = fake_cursor.executed[0]
    assert "data_source LIKE 'official_source:%%'" in sql
    assert params == (50,)


def test_pending_artifact_records_exclude_candidates_already_verified_in_index(monkeypatch):
    fake_cursor = _FakeCursor()
    monkeypatch.setattr(
        repository_module,
        "get_cursor",
        lambda: _CursorContext(fake_cursor),
    )

    SourceRecordRepository.list_pending_artifact_records(limit=20)

    sql, params = fake_cursor.executed[0]
    assert "NOT EXISTS" in sql
    assert "ci_existing.authenticity_status = 'verified'" in sql
    assert "ci_existing.official_url IN (sr.source_url, sr.artifact_url)" in sql
    assert "lower(btrim(ci_existing.name)) = lower(btrim(sr.title))" in sql
    assert "similarity(ci_existing.name, sr.title) >= 0.72" in sql
    assert "ci_existing.entry_type::text = sr.entry_type::text" in sql
    assert params == (20,)


def test_compliance_create_defaults_to_candidate_review_state():
    data = {
        "name": "Candidate Rule",
        "entry_type": "regulation",
        "country_code": "EU",
    }

    _ensure_compliance_create_review_gate(data)

    assert data["verified"] is False
    assert data["authenticity_status"] == "candidate"
    assert data["authenticity_risk_score"] >= 50
    assert "requires_review_before_verified" in data["authenticity_reasons"]


def test_compliance_create_rejects_verified_without_official_artifact():
    data = {
        "name": "Fake Verified Rule",
        "entry_type": "regulation",
        "country_code": "EU",
        "verified": True,
        "authenticity_status": "verified",
        "official_url": "https://example.gov/rule",
        "authenticity_evidence": "manual note",
    }

    try:
        _ensure_compliance_create_review_gate(data)
    except ValueError as exc:
        assert "verified 入库必须带官方证据链" in str(exc)
    else:
        raise AssertionError("verified creation without artifact should be rejected")


def test_verified_review_requires_evidence_note_and_source_artifact():
    record = {
        "id": "rec-1",
        "official_url": "https://example.gov/rule",
        "source_artifact_sha256": "abc123",
    }

    _ensure_verified_review_gate(
        record,
        authenticity_status="verified",
        evidence="2026-04-28 官方 PDF 已下载并校验哈希。",
    )

    try:
        _ensure_verified_review_gate(
            {"id": "rec-2", "official_url": "https://example.gov/rule"},
            authenticity_status="verified",
            evidence="2026-04-28 官方页面存在。",
        )
    except ValueError as exc:
        assert "verified 审核必须先完成官方原文工件闭环" in str(exc)
    else:
        raise AssertionError("verified review without artifact should be rejected")
