from collector.document import retrieval_service as retrieval_module
from collector.document.retrieval_service import RetrievalService
from database.repository import _verified_document_filter_sql


class _FakeEmbedder:
    calls = []

    def embed_texts(self, texts):
        self.calls.append(list(texts))
        return [[0.1, 0.2, 0.3]]


class _FakeSectionRepository:
    @staticmethod
    def section_search(**kwargs):
        return [
            {
                "document_id": "doc-1",
                "document_name": "CRA",
                "chunk_index": 0,
                "page_from": 12,
                "page_to": 12,
                "section_score": 1.0,
                "clause_ref": "Article 13",
                "content": "Default security settings.",
                "country_code": "EU",
                "compliance_id": "11111111-1111-1111-1111-111111111111",
            }
        ]


class _FakeChunkRepository:
    @staticmethod
    def vector_search(**kwargs):
        return []

    @staticmethod
    def keyword_search(**kwargs):
        return []


class _EmptySpecRepository:
    @staticmethod
    def search_for_rag(**kwargs):
        return []


def test_retrieval_service_uses_section_repository():
    from database.repository import ComplianceIndexRepository

    original = ComplianceIndexRepository.list_by_ids
    ComplianceIndexRepository.list_by_ids = staticmethod(lambda record_ids, verified_only=True: [])
    service = RetrievalService(
        embedder=_FakeEmbedder(),
        section_repository=_FakeSectionRepository,
        chunk_repository=_FakeChunkRepository,
        spec_repository=_EmptySpecRepository,
    )

    try:
        result = service.retrieve("CRA 默认安全配置要求", country_code="EU", verified_only=True, top_k=3)
    finally:
        ComplianceIndexRepository.list_by_ids = original

    assert result["trace"]["retrieval_counts"]["section_hits"] == 1
    assert result["hits"][0]["clause_ref"] == "Article 13"


def test_verified_document_filter_allows_documents_linked_to_verified_compliance():
    sql = _verified_document_filter_sql("c.document_id")

    assert "ci.document_id = c.document_id" in sql
    assert "d.compliance_id = ci.compliance_id" in sql
    assert "d.id = c.document_id" in sql


def test_retrieval_service_expands_chinese_network_device_query_for_official_english_corpus():
    from database.repository import ComplianceIndexRepository

    captured = {}

    class _NoSectionRepo:
        @staticmethod
        def section_search(**kwargs):
            return []

    class _ChunkRepo:
        @staticmethod
        def vector_search(**kwargs):
            captured["query_vector"] = kwargs["query_vector"]
            return []

        @staticmethod
        def keyword_search(**kwargs):
            captured["keyword"] = kwargs["keyword"]
            return []

    embedder = _FakeEmbedder()
    service = RetrievalService(
        embedder=embedder,
        section_repository=_NoSectionRepo,
        chunk_repository=_ChunkRepo,
        spec_repository=_EmptySpecRepository,
    )

    original = ComplianceIndexRepository.list_by_country
    original_product = ComplianceIndexRepository.list_by_product
    ComplianceIndexRepository.list_by_country = staticmethod(lambda country_code, verified_only=True, limit=5: [])
    ComplianceIndexRepository.list_by_product = staticmethod(lambda product_code, country_code=None, verified_only=True, limit=5: [])
    try:
        service.retrieve("美国对交换机产品有什么要求", country_code="US", verified_only=True)
    finally:
        ComplianceIndexRepository.list_by_country = original
        ComplianceIndexRepository.list_by_product = original_product

    assert "Protection Profile for Network Devices" in embedder.calls[-1][0]
    assert captured["keyword"] == "Protection Profile Network Devices security functional requirements"


def test_retrieval_service_infers_product_code_from_chinese_question():
    from database.repository import ComplianceIndexRepository

    captured = {}

    class _NoSectionRepo:
        @staticmethod
        def section_search(**kwargs):
            return []

    class _ChunkRepo:
        @staticmethod
        def vector_search(**kwargs):
            return []

        @staticmethod
        def keyword_search(**kwargs):
            return []

    class _SpecRepo:
        @staticmethod
        def search_for_rag(**kwargs):
            captured["product_code"] = kwargs["product_code"]
            return []

    original = ComplianceIndexRepository.list_by_country
    original_product = ComplianceIndexRepository.list_by_product
    ComplianceIndexRepository.list_by_country = staticmethod(lambda country_code, verified_only=True, limit=5: [])
    ComplianceIndexRepository.list_by_product = staticmethod(lambda product_code, country_code=None, verified_only=True, limit=5: [])
    try:
        service = RetrievalService(
            embedder=_FakeEmbedder(),
            section_repository=_NoSectionRepo,
            chunk_repository=_ChunkRepo,
            spec_repository=_SpecRepo,
        )
        result = service.retrieve("美国对交换机产品有什么网络安全要求", country_code="US", verified_only=True)
    finally:
        ComplianceIndexRepository.list_by_country = original
        ComplianceIndexRepository.list_by_product = original_product

    assert captured["product_code"] == "switch"
    assert result["trace"]["filters"]["inferred_product_code"] == "switch"


def test_retrieval_service_uses_cn_product_certification_keywords():
    from database.repository import ComplianceIndexRepository

    captured = {}

    class _NoSectionRepo:
        @staticmethod
        def section_search(**kwargs):
            return []

    class _ChunkRepo:
        @staticmethod
        def vector_search(**kwargs):
            return []

        @staticmethod
        def keyword_search(**kwargs):
            captured["keyword"] = kwargs["keyword"]
            return []

    service = RetrievalService(
        embedder=_FakeEmbedder(),
        section_repository=_NoSectionRepo,
        chunk_repository=_ChunkRepo,
        spec_repository=_EmptySpecRepository,
    )

    original = ComplianceIndexRepository.list_by_country
    ComplianceIndexRepository.list_by_country = staticmethod(lambda country_code, verified_only=True, limit=5: [])
    try:
        service.retrieve("中国网络关键设备和专用网络安全产品有哪些强制要求？", country_code="CN", verified_only=True)
    finally:
        ComplianceIndexRepository.list_by_country = original

    assert "网络关键设备" in captured["keyword"]
    assert "专用网络安全产品" in captured["keyword"]
    assert "认证" in captured["keyword"]


def test_retrieval_service_uses_psti_keywords_present_in_official_text():
    from database.repository import ComplianceIndexRepository

    captured = {}

    class _NoSectionRepo:
        @staticmethod
        def section_search(**kwargs):
            return []

    class _ChunkRepo:
        @staticmethod
        def vector_search(**kwargs):
            return []

        @staticmethod
        def keyword_search(**kwargs):
            captured["keyword"] = kwargs["keyword"]
            return []

    service = RetrievalService(
        embedder=_FakeEmbedder(),
        section_repository=_NoSectionRepo,
        chunk_repository=_ChunkRepo,
        spec_repository=_EmptySpecRepository,
    )

    original = ComplianceIndexRepository.list_by_country
    ComplianceIndexRepository.list_by_country = staticmethod(lambda country_code, verified_only=True, limit=5: [])
    try:
        service.retrieve("英国PSTI对产品有什么要求？", country_code="GB", verified_only=True)
    finally:
        ComplianceIndexRepository.list_by_country = original

    assert captured["keyword"] == "Product Security security requirements"


def test_retrieval_service_infers_country_code_from_question_text(monkeypatch):
    from database.repository import ComplianceIndexRepository

    captured = {}

    class _Cursor:
        def execute(self, sql, params=None):
            pass

        def fetchall(self):
            return [
                {"code": "GB", "name_zh": "英国", "name_en": "United Kingdom"},
                {"code": "US", "name_zh": "美国", "name_en": "United States"},
            ]

    class _Context:
        def __enter__(self):
            return _Cursor()

        def __exit__(self, exc_type, exc, tb):
            return False

    class _NoSectionRepo:
        @staticmethod
        def section_search(**kwargs):
            captured["section_country_code"] = kwargs["country_code"]
            return []

    class _ChunkRepo:
        @staticmethod
        def vector_search(**kwargs):
            captured["vector_country_code"] = kwargs["country_code"]
            return []

        @staticmethod
        def keyword_search(**kwargs):
            captured["keyword_country_code"] = kwargs["country_code"]
            return []

    monkeypatch.setattr(retrieval_module, "get_cursor", lambda: _Context(), raising=False)
    if hasattr(RetrievalService, "_country_hints") and hasattr(RetrievalService._country_hints, "cache_clear"):
        RetrievalService._country_hints.cache_clear()
    original = ComplianceIndexRepository.list_by_country
    ComplianceIndexRepository.list_by_country = staticmethod(lambda country_code, verified_only=True, limit=5: [])
    try:
        service = RetrievalService(
            embedder=_FakeEmbedder(),
            section_repository=_NoSectionRepo,
            chunk_repository=_ChunkRepo,
            spec_repository=_EmptySpecRepository,
        )
        result = service.retrieve("英国PSTI对产品有什么要求？", verified_only=True)
    finally:
        ComplianceIndexRepository.list_by_country = original

    assert result["trace"]["filters"]["inferred_country_code"] == "GB"
    assert captured["keyword_country_code"] == "GB"
    assert captured["vector_country_code"] == "GB"
    assert captured["section_country_code"] == "GB"


def test_retrieval_service_boosts_network_device_evidence_above_broad_iot_specs():
    from database.repository import ComplianceIndexRepository

    class _NoSectionRepo:
        @staticmethod
        def section_search(**kwargs):
            return []

    class _ChunkRepo:
        @staticmethod
        def vector_search(**kwargs):
            return []

        @staticmethod
        def keyword_search(**kwargs):
            return [
                {
                    "document_id": "doc-niap",
                    "document_name": "US NIAP Common Criteria Evaluation and Validation Scheme",
                    "chunk_index": 10,
                    "page_from": 43,
                    "page_to": 43,
                    "section_path": None,
                    "clause_ref": "Section 6",
                    "content": "Security Functional Requirements for Network Devices, including routers and switches.",
                    "country_code": "US",
                    "compliance_id": "record-niap",
                    "keyword_score": 0.2,
                }
            ]

        @staticmethod
        def list_by_ids(chunk_ids):
            return []

        @staticmethod
        def list_by_document_pages(document_id, pages, limit=3):
            return [
                {
                    "id": "chunk-fcc",
                    "document_id": "doc-fcc",
                    "document_name": "Cyber Trust Mark Program Final Rule",
                    "chunk_index": 24,
                    "page_from": 24,
                    "page_to": 24,
                    "section_path": None,
                    "clause_ref": "§ 8.220(g)",
                    "content": "The IoT labeling program includes post-market surveillance requirements.",
                    "country_code": "US",
                    "compliance_id": "record-fcc",
                }
            ]

    class _SpecRepo:
        @staticmethod
        def search_for_rag(**kwargs):
            return [
                {
                    "id": "spec-fcc",
                    "document_id": "doc-fcc",
                    "compliance_id": "record-fcc",
                    "country_code": "US",
                    "regulation_name": "Cyber Trust Mark Program Final Rule",
                    "req_id": "CMP-FCC-002",
                    "title_zh": "上市后监督",
                    "description_zh": "产品应接受上市后监督。",
                    "applicable_products": ["switch"],
                    "mandatory": "mandatory",
                    "priority": "P1",
                    "regulation_clause": "§ 8.220(g)",
                    "source_pages": "24",
                    "source_chunk_ids": "{}",
                    "spec_score": 0.45,
                }
            ]

    original = ComplianceIndexRepository.list_by_ids
    ComplianceIndexRepository.list_by_ids = staticmethod(lambda record_ids, verified_only=True: [])
    try:
        service = RetrievalService(
            embedder=_FakeEmbedder(),
            section_repository=_NoSectionRepo,
            chunk_repository=_ChunkRepo,
            spec_repository=_SpecRepo,
        )
        result = service.retrieve("美国对交换机产品有什么网络安全要求", country_code="US", verified_only=True)
    finally:
        ComplianceIndexRepository.list_by_ids = original

    assert result["hits"][0]["document_id"] == "doc-niap"
    assert result["hits"][0]["doc_score"] > 0


def test_retrieval_service_resolves_stale_document_scope_before_search():
    from database.repository import ComplianceIndexRepository

    captured = {}

    class _NoSectionRepo:
        @staticmethod
        def section_search(**kwargs):
            captured["section_document_id"] = kwargs["document_id"]
            return []

    class _ChunkRepo:
        @staticmethod
        def resolve_ready_document_scope(doc_id):
            captured["requested_document_id"] = doc_id
            return "ready-doc"

        @staticmethod
        def vector_search(**kwargs):
            captured["vector_document_id"] = kwargs["document_id"]
            return []

        @staticmethod
        def keyword_search(**kwargs):
            captured["keyword_document_id"] = kwargs["document_id"]
            return []

    service = RetrievalService(
        embedder=_FakeEmbedder(),
        section_repository=_NoSectionRepo,
        chunk_repository=_ChunkRepo,
        spec_repository=_EmptySpecRepository,
    )
    original = ComplianceIndexRepository.list_by_country
    original_product = ComplianceIndexRepository.list_by_product
    ComplianceIndexRepository.list_by_country = staticmethod(lambda country_code, verified_only=True, limit=5: [])
    ComplianceIndexRepository.list_by_product = staticmethod(lambda product_code, country_code=None, verified_only=True, limit=5: [])
    try:
        result = service.retrieve(
            "美国对交换机产品有什么要求",
            country_code="US",
            document_id="stale-doc",
            verified_only=True,
        )
    finally:
        ComplianceIndexRepository.list_by_country = original
        ComplianceIndexRepository.list_by_product = original_product

    assert captured["requested_document_id"] == "stale-doc"
    assert captured["section_document_id"] == "ready-doc"
    assert captured["vector_document_id"] == "ready-doc"
    assert captured["keyword_document_id"] == "ready-doc"
    assert result["trace"]["filters"]["requested_document_id"] == "stale-doc"
    assert result["trace"]["filters"]["document_id"] == "ready-doc"


def test_retrieval_service_uses_spec_requirements_as_grounded_evidence_hints():
    from database.repository import ComplianceIndexRepository

    captured = {}

    class _NoSectionRepo:
        @staticmethod
        def section_search(**kwargs):
            return []

    class _ChunkRepo:
        @staticmethod
        def vector_search(**kwargs):
            return []

        @staticmethod
        def keyword_search(**kwargs):
            return []

        @staticmethod
        def list_by_ids(chunk_ids):
            captured["chunk_ids"] = chunk_ids
            return [
                {
                    "id": "chunk-1",
                    "document_id": "doc-1",
                    "document_name": "US NIAP Network Device cPP",
                    "chunk_index": 42,
                    "page_from": 43,
                    "page_to": 43,
                    "section_path": "6. Security Functional Requirements",
                    "clause_ref": "Section 6",
                    "content": "The TOE shall satisfy the Security Functional Requirements for Network Devices.",
                    "country_code": "US",
                    "compliance_id": "record-1",
                }
            ]

    class _SpecRepo:
        @staticmethod
        def search_for_rag(**kwargs):
            captured["spec_query"] = kwargs
            return [
                {
                    "id": "spec-1",
                    "document_id": "doc-1",
                    "compliance_id": "record-1",
                    "country_code": "US",
                    "regulation_name": "US NIAP Network Device cPP",
                    "req_id": "ND-SFR-1",
                    "module_zh": "安全功能要求",
                    "title_zh": "网络设备安全功能要求",
                    "description_zh": "网络设备需要满足安全功能要求。",
                    "verification_method_zh": "按支持文档中的评估活动验证。",
                    "mandatory": "mandatory",
                    "priority": "P0",
                    "regulation_clause": "Section 6",
                    "source_pages": "43",
                    "source_chunk_ids": ["chunk-1"],
                    "spec_score": 1.0,
                }
            ]

    original = ComplianceIndexRepository.list_by_ids
    ComplianceIndexRepository.list_by_ids = staticmethod(
        lambda record_ids, verified_only=True: [
            {
                "id": "record-1",
                "name": "US NIAP Common Criteria Evaluation and Validation Scheme",
                "entry_type": "certification",
                "country_code": "US",
            }
        ]
    )
    try:
        service = RetrievalService(
            embedder=_FakeEmbedder(),
            section_repository=_NoSectionRepo,
            chunk_repository=_ChunkRepo,
            spec_repository=_SpecRepo,
        )
        result = service.retrieve("美国对交换机产品有什么要求", country_code="US", verified_only=True)
    finally:
        ComplianceIndexRepository.list_by_ids = original

    assert captured["spec_query"]["country_code"] == "US"
    assert captured["chunk_ids"] == ["chunk-1"]
    assert result["trace"]["retrieval_counts"]["spec_hits"] == 1
    assert result["hits"][0]["document_id"] == "doc-1"
    assert result["hits"][0]["spec_context"]["req_id"] == "ND-SFR-1"
    assert result["hits"][0]["score"] >= 1.0


def test_retrieval_service_ignores_empty_postgres_array_string_from_legacy_specs():
    from database.repository import ComplianceIndexRepository

    class _NoSectionRepo:
        @staticmethod
        def section_search(**kwargs):
            return []

    class _ChunkRepo:
        @staticmethod
        def vector_search(**kwargs):
            return []

        @staticmethod
        def keyword_search(**kwargs):
            return []

        @staticmethod
        def list_by_ids(chunk_ids):
            raise AssertionError("empty source_chunk_ids should not be resolved")

    class _SpecRepo:
        @staticmethod
        def search_for_rag(**kwargs):
            return [
                {
                    "id": "spec-legacy",
                    "document_id": "doc-1",
                    "source_chunk_ids": "{}",
                    "spec_score": 1.0,
                }
            ]

    service = RetrievalService(
        embedder=_FakeEmbedder(),
        section_repository=_NoSectionRepo,
        chunk_repository=_ChunkRepo,
        spec_repository=_SpecRepo,
    )

    original = ComplianceIndexRepository.list_by_country
    original_product = ComplianceIndexRepository.list_by_product
    ComplianceIndexRepository.list_by_country = staticmethod(lambda country_code, verified_only=True, limit=5: [])
    ComplianceIndexRepository.list_by_product = staticmethod(lambda product_code, country_code=None, verified_only=True, limit=5: [])
    try:
        result = service.retrieve("美国对交换机产品有什么要求", country_code="US", verified_only=True)
    finally:
        ComplianceIndexRepository.list_by_country = original
        ComplianceIndexRepository.list_by_product = original_product

    assert result["trace"]["retrieval_counts"]["spec_hits"] == 1
    assert result["trace"]["retrieval_counts"]["spec_evidence_hits"] == 0


def test_retrieval_service_grounds_legacy_specs_by_source_pages_when_chunk_ids_missing():
    from database.repository import ComplianceIndexRepository

    captured = {}

    class _NoSectionRepo:
        @staticmethod
        def section_search(**kwargs):
            return []

    class _ChunkRepo:
        @staticmethod
        def vector_search(**kwargs):
            return []

        @staticmethod
        def keyword_search(**kwargs):
            return []

        @staticmethod
        def list_by_ids(chunk_ids):
            return []

        @staticmethod
        def list_by_document_pages(document_id, pages, limit=3):
            captured["document_id"] = document_id
            captured["pages"] = pages
            return [
                {
                    "id": "chunk-page-24",
                    "document_id": document_id,
                    "document_name": "Cyber Trust Mark Program Final Rule",
                    "chunk_index": 24,
                    "page_from": 24,
                    "page_to": 24,
                    "section_path": None,
                    "clause_ref": "§ 8.220(g)",
                    "content": "The program includes post-market surveillance requirements.",
                    "country_code": "US",
                    "compliance_id": "record-ctm",
                }
            ]

    class _SpecRepo:
        @staticmethod
        def search_for_rag(**kwargs):
            return [
                {
                    "id": "spec-page",
                    "document_id": "doc-ctm",
                    "compliance_id": "record-ctm",
                    "country_code": "US",
                    "regulation_name": "Cyber Trust Mark Program Final Rule",
                    "req_id": "CMP-FCC-002",
                    "title_zh": "上市后监督",
                    "description_zh": "产品应接受上市后监督。",
                    "mandatory": "mandatory",
                    "priority": "P0",
                    "regulation_clause": "§ 8.220(g)",
                    "source_pages": "24",
                    "source_chunk_ids": "{}",
                    "spec_score": 1.0,
                }
            ]

    original = ComplianceIndexRepository.list_by_ids
    ComplianceIndexRepository.list_by_ids = staticmethod(lambda record_ids, verified_only=True: [])
    try:
        service = RetrievalService(
            embedder=_FakeEmbedder(),
            section_repository=_NoSectionRepo,
            chunk_repository=_ChunkRepo,
            spec_repository=_SpecRepo,
        )
        result = service.retrieve("美国 Cyber Trust Mark 上市后监督要求", country_code="US", verified_only=True)
    finally:
        ComplianceIndexRepository.list_by_ids = original

    assert captured["document_id"] == "doc-ctm"
    assert captured["pages"] == [24]
    assert result["trace"]["retrieval_counts"]["spec_evidence_hits"] == 1
    assert result["hits"][0]["spec_context"]["req_id"] == "CMP-FCC-002"
