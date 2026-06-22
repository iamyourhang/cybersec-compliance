from database import repository as repository_module
from database.repository import RegulationSpecRequirementRepository


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def cursor(self):
        return _FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_spec_requirement_upsert_clamps_varchar_fields(monkeypatch):
    captured = {}

    monkeypatch.setattr(repository_module, "get_connection", lambda: _FakeConnection())
    monkeypatch.setattr(
        repository_module.psycopg2.extras,
        "execute_batch",
        lambda cur, sql, payloads, page_size=100: captured.update({"payloads": payloads}),
    )

    RegulationSpecRequirementRepository.upsert_many(
        [
            {
                "document_id": "doc-1",
                "compliance_id": "rec-1",
                "country_code": "LV",
                "regulation_name": "R" * 260,
                "req_id": "REQ-" + "1" * 120,
                "module_zh": "模" * 150,
                "module_en": "Module " * 40,
                "title_zh": "标题" * 130,
                "title_en": "Title " * 60,
                "description_zh": "描述不应被截断",
                "description_en": "Long text fields should remain untouched.",
                "applicable_products": ["software"],
                "mandatory": "mandatory-value-too-long",
                "priority": "priority-value-too-long",
                "regulation_clause": "Article " + "1" * 260,
                "source_pages": "1-" + "2" * 200,
                "source_chunk_ids": [],
            }
        ]
    )

    payload = captured["payloads"][0]
    assert len(payload[3]) <= 300
    assert len(payload[4]) <= 80
    assert len(payload[5]) <= 120
    assert len(payload[6]) <= 120
    assert len(payload[7]) <= 200
    assert len(payload[8]) <= 200
    assert len(payload[12]) <= 20
    assert len(payload[13]) <= 10
    assert len(payload[14]) <= 120
    assert len(payload[19]) <= 120
    assert payload[9] == "描述不应被截断"
