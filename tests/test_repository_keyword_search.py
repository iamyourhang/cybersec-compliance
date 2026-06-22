from database import repository


def test_chunk_keyword_search_falls_back_to_ilike_for_chinese_terms(monkeypatch):
    class _Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))

        def fetchall(self):
            if len(self.calls) == 1:
                return []
            return [
                {
                    "document_id": "doc-cn",
                    "document_name": "中华人民共和国网络安全法（2025年修正）",
                    "chunk_index": 25,
                    "page_from": 1,
                    "page_to": 1,
                    "section_path": None,
                    "clause_ref": "第二十五条",
                    "content": "网络关键设备和网络安全专用产品应当经过安全认证或安全检测。",
                    "country_code": "CN",
                    "compliance_id": "record-cn",
                    "keyword_score": 0.45,
                }
            ]

    cursor = _Cursor()

    class _Context:
        def __enter__(self):
            return cursor

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(repository, "get_cursor", lambda: _Context())

    rows = repository.RegulationChunkRepository.keyword_search(
        "网络关键设备 专用网络安全产品 认证 检测 目录 强制 安全",
        country_code="CN",
        verified_only=True,
        limit=20,
    )

    assert len(cursor.calls) == 2
    fallback_sql, fallback_params = cursor.calls[1]
    assert "ILIKE" in fallback_sql
    assert "ci.authenticity_status = 'verified'" in fallback_sql
    assert "%网络安全专用产品%" in fallback_params
    assert rows[0]["clause_ref"] == "第二十五条"
