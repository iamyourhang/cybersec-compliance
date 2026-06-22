from collector.document.answer_service import AnswerService
from collector.providers.base import LLMResponse


def test_answer_service_returns_insufficient_evidence_without_strong_hits():
    service = AnswerService()

    trace = {"grounding_mode": "verified_local_corpus"}
    result = service.answer(
        question="CRA 对防火墙的默认安全要求有哪些？",
        hits=[
            {
                "score": 0.31,
                "keyword_score": 0.0,
                "vector_score": 0.31,
                "document_id": "doc-1",
                "document_name": "CRA",
                "page_from": 10,
                "page_to": 10,
                "clause_ref": "Article 10",
                "content": "本条主要定义术语。",
                "country_code": "EU",
            }
        ],
        related_records=[],
        trace=trace,
    )

    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []
    assert result["trace"] == trace
    assert result["next_actions"]


def test_answer_service_formats_citations_from_grounded_summary():
    service = AnswerService(
        summarizer=lambda question, hits, related_records, history: "法规要求提供默认安全配置，并支持安全更新。",
    )

    result = service.answer(
        question="CRA 对防火墙的默认安全要求有哪些？",
        hits=[
            {
                "score": 0.88,
                "keyword_score": 0.73,
                "vector_score": 0.91,
                "document_id": "doc-1",
                "document_name": "Cyber Resilience Act",
                "page_from": 12,
                "page_to": 13,
                "clause_ref": "Article 10",
                "content": "Products shall be placed on the market with secure by default configurations.",
                "country_code": "EU",
            },
            {
                "score": 0.77,
                "keyword_score": 0.68,
                "vector_score": 0.8,
                "document_id": "doc-1",
                "document_name": "Cyber Resilience Act",
                "page_from": 13,
                "page_to": 13,
                "clause_ref": "Article 13",
                "content": "Manufacturers shall ensure vulnerabilities can be addressed through security updates.",
                "country_code": "EU",
            },
        ],
        related_records=[
            {
                "id": "rec-1",
                "name": "Cyber Resilience Act",
                "entry_type": "regulation",
                "country_code": "EU",
            }
        ],
        history=[{"role": "user", "content": "先看 CRA"}],
        trace={"grounding_mode": "verified_local_corpus"},
    )

    assert result["status"] == "answered"
    assert "默认安全配置" in result["answer"]
    assert result["citations"][0]["clause_ref"] == "Article 10"
    assert result["related_records"][0]["name"] == "Cyber Resilience Act"
    assert result["trace"]["grounding_mode"] == "verified_local_corpus"
    assert result["next_actions"]


def test_answer_service_allows_document_scoped_vector_evidence():
    service = AnswerService(
        summarizer=lambda question, hits, related_records, history: "根据限定文档证据，实体需采取适当且相称的网络安全风险管理措施。",
    )

    result = service.answer(
        question="§ 6 风险管理措施有哪些？",
        hits=[
            {
                "score": 0.36,
                "keyword_score": 0.0,
                "vector_score": 0.44,
                "document_id": "doc-dk",
                "document_name": "Denmark NIS 2 Act",
                "page_from": 7,
                "page_to": 7,
                "clause_ref": "§ 6",
                "content": "Væsentlige og vigtige enheder skal træffe passende og forholdsmæssige tekniske, operationelle og organisatoriske foranstaltninger.",
                "country_code": "DK",
            },
            {
                "score": 0.32,
                "keyword_score": 0.0,
                "vector_score": 0.36,
                "document_id": "doc-dk",
                "document_name": "Denmark NIS 2 Act",
                "page_from": 7,
                "page_to": 8,
                "clause_ref": "§ 6",
                "content": "Foranstaltningerne omfatter bl.a. politikker for risikoanalyse, hændelseshåndtering og forsyningskædesikkerhed.",
                "country_code": "DK",
            },
        ],
        related_records=[],
        trace={
            "grounding_mode": "verified_local_corpus",
            "filters": {"document_id": "doc-dk"},
        },
    )

    assert result["status"] == "answered"
    assert result["citations"][0]["document_id"] == "doc-dk"


def test_answer_service_allows_multiple_verified_country_scoped_chunk_hits():
    service = AnswerService(
        summarizer=lambda question, hits, related_records, history: "根据已验证原文片段，美国 NIAP/CC 网络设备保护轮廓列出了安全功能要求。",
    )

    result = service.answer(
        question="美国对交换机产品有什么要求？",
        hits=[
            {
                "score": 0.12,
                "keyword_score": 0.01,
                "vector_score": 0.0,
                "document_id": "doc-us",
                "document_name": "US NIAP Network Device cPP",
                "page_from": 43,
                "page_to": 43,
                "clause_ref": "6",
                "content": "6. Security Functional Requirements for Network Devices.",
                "country_code": "US",
            },
            {
                "score": 0.11,
                "keyword_score": 0.01,
                "vector_score": 0.0,
                "document_id": "doc-us",
                "document_name": "US NIAP Network Device cPP",
                "page_from": 44,
                "page_to": 45,
                "clause_ref": "6.1",
                "content": "The TOE shall enforce secure management and cryptographic support requirements.",
                "country_code": "US",
            },
        ],
        related_records=[],
        trace={
            "grounding_mode": "verified_local_corpus",
            "verified_only": True,
            "filters": {"country_code": "US", "document_id": None},
            "retrieval_counts": {"merged_hits": 2},
        },
    )

    assert result["status"] == "answered"
    assert result["citations"][0]["document_id"] == "doc-us"


def test_answer_service_does_not_count_freshness_only_hits_as_strong_evidence():
    service = AnswerService(
        summarizer=lambda question, hits, related_records, history: "不应调用",
    )

    result = service.answer(
        question="中国网络关键设备和专用网络安全产品有哪些强制要求？",
        hits=[
            {
                "score": 0.1,
                "keyword_score": 0.0,
                "vector_score": 0.0,
                "section_score": 0.0,
                "spec_score": 0.0,
                "document_id": "doc-cn",
                "document_name": "中华人民共和国网络安全法",
                "page_from": 1,
                "page_to": 1,
                "clause_ref": "第六十条",
                "content": "因维护国家安全和社会公共秩序，可以在特定区域对网络通信采取限制等临时措施。",
                "country_code": "CN",
            },
            {
                "score": 0.1,
                "keyword_score": 0.0,
                "vector_score": 0.0,
                "section_score": 0.0,
                "spec_score": 0.0,
                "document_id": "doc-cn",
                "document_name": "关键信息基础设施安全保护条例",
                "page_from": 1,
                "page_to": 1,
                "clause_ref": "第六条",
                "content": "运营者应采取技术保护措施。",
                "country_code": "CN",
            },
        ],
        related_records=[],
        trace={
            "grounding_mode": "verified_local_corpus",
            "verified_only": True,
            "retrieval_counts": {"merged_hits": 2},
        },
    )

    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []


def test_answer_service_default_summarizer_uses_channel_router():
    used = {}

    class _FakeRouter:
        def chat(self, **kwargs):
            used["called"] = True
            return LLMResponse(
                content="法规要求提供默认安全配置，并支持安全更新。",
                provider_name="fake",
                model="fake-model",
            )

    service = AnswerService(router=_FakeRouter())

    result = service.answer(
        question="CRA 对防火墙的默认安全要求有哪些？",
        hits=[
            {
                "score": 0.88,
                "keyword_score": 0.73,
                "vector_score": 0.91,
                "document_id": "doc-1",
                "document_name": "Cyber Resilience Act",
                "page_from": 12,
                "page_to": 13,
                "clause_ref": "Article 10",
                "content": "Products shall be placed on the market with secure by default configurations.",
                "country_code": "EU",
            },
            {
                "score": 0.77,
                "keyword_score": 0.68,
                "vector_score": 0.8,
                "document_id": "doc-1",
                "document_name": "Cyber Resilience Act",
                "page_from": 13,
                "page_to": 13,
                "clause_ref": "Article 13",
                "content": "Manufacturers shall ensure vulnerabilities can be addressed through security updates.",
                "country_code": "EU",
            },
        ],
        related_records=[],
        history=[{"role": "user", "content": "聚焦 Article 10"}],
    )

    assert result["status"] == "answered"
    assert used["called"] is True


def test_answer_service_prompt_enforces_verified_local_evidence_boundary():
    captured = {}

    class _FakeRouter:
        def chat(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return LLMResponse(
                content="现有证据表明该法规要求提供默认安全配置。",
                provider_name="fake",
                model="fake-model",
            )

    service = AnswerService(router=_FakeRouter())

    service.answer(
        question="这条要求是否真实且强制？",
        hits=[
            {
                "score": 0.91,
                "keyword_score": 0.7,
                "vector_score": 0.9,
                "document_id": "doc-1",
                "document_name": "CRA",
                "page_from": 12,
                "page_to": 13,
                "clause_ref": "Article 10",
                "content": "Products shall be placed on the market with secure by default configurations.",
                "country_code": "EU",
            },
            {
                "score": 0.82,
                "keyword_score": 0.64,
                "vector_score": 0.84,
                "document_id": "doc-1",
                "document_name": "CRA",
                "page_from": 14,
                "page_to": 14,
                "clause_ref": "Annex I",
                "content": "Manufacturers shall ensure vulnerabilities can be addressed.",
                "country_code": "EU",
            },
        ],
        related_records=[],
    )

    prompt = captured["messages"][0]["content"]
    assert "禁止把候选、可疑、联网搜索或训练记忆当成证据" in prompt
    assert "只能基于提供的证据作答" in prompt
    assert "交换机、路由器、网络设备" in prompt


def test_answer_service_includes_spec_context_but_cites_original_excerpt():
    captured = {}

    def summarizer(question, hits, related_records, history):
        captured["hits"] = hits
        return "结论：需要满足网络设备安全功能要求。"

    service = AnswerService(summarizer=summarizer)
    result = service.answer(
        "美国对交换机产品有什么要求",
        hits=[
            {
                "document_id": "doc-1",
                "document_name": "US NIAP Network Device cPP",
                "chunk_index": 42,
                "page_from": 43,
                "page_to": 43,
                "clause_ref": "Section 6",
                "content": "Original clause evidence from Section 6.",
                "country_code": "US",
                "compliance_id": "record-1",
                "score": 1.2,
                "spec_context": {
                    "req_id": "ND-SFR-1",
                    "title_zh": "网络设备安全功能要求",
                    "description_zh": "网络设备需要满足安全功能要求。",
                },
            },
            {
                "document_id": "doc-1",
                "document_name": "US NIAP Network Device cPP",
                "chunk_index": 43,
                "page_from": 44,
                "page_to": 44,
                "clause_ref": "Section 6.1",
                "content": "Second original clause evidence.",
                "country_code": "US",
                "compliance_id": "record-1",
                "score": 1.1,
            },
        ],
        related_records=[],
        trace={"verified_only": True, "retrieval_counts": {"merged_hits": 2}, "filters": {"country_code": "US"}},
    )

    assert result["status"] == "answered"
    assert captured["hits"][0]["spec_context"]["req_id"] == "ND-SFR-1"
    assert result["citations"][0]["excerpt"] == "Original clause evidence from Section 6."


def test_answer_service_normalizes_model_insufficient_answer_status():
    service = AnswerService(
        summarizer=lambda question, hits, related_records, history: "现有原文证据不足以确认该结论。",
    )

    result = service.answer(
        question="美国对交换机产品有什么要求？",
        hits=[
            {
                "score": 0.88,
                "keyword_score": 0.73,
                "vector_score": 0.91,
                "document_id": "doc-1",
                "document_name": "US NIAP Network Device cPP",
                "page_from": 43,
                "page_to": 43,
                "clause_ref": "6",
                "content": "Security Functional Requirements for Network Devices.",
                "country_code": "US",
            },
            {
                "score": 0.77,
                "keyword_score": 0.68,
                "vector_score": 0.8,
                "document_id": "doc-1",
                "document_name": "US NIAP Network Device cPP",
                "page_from": 44,
                "page_to": 44,
                "clause_ref": "6.1",
                "content": "The TOE shall enforce security management requirements.",
                "country_code": "US",
            },
        ],
        related_records=[],
        trace={"grounding_mode": "verified_local_corpus"},
    )

    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []


def test_answer_service_normalizes_insufficient_answer_with_extra_explanation():
    service = AnswerService(
        summarizer=lambda question, hits, related_records, history: "现有原文证据不足以确认该结论。\n\n分析说明：规格库提示存在，但原文不足。",
    )

    result = service.answer(
        question="美国 Cyber Trust Mark 上市后监督要求是什么？",
        hits=[
            {
                "score": 1.1,
                "document_id": "doc-1",
                "document_name": "Cyber Trust Mark Program Final Rule",
                "page_from": 24,
                "page_to": 24,
                "clause_ref": "§ 8.220(g)",
                "content": "Lead Administrators shall be responsible for developing post-market surveillance procedures.",
                "country_code": "US",
            },
            {
                "score": 1.0,
                "document_id": "doc-1",
                "document_name": "Cyber Trust Mark Program Final Rule",
                "page_from": 25,
                "page_to": 25,
                "clause_ref": "§ 8.220(g)",
                "content": "The Commission may review procedures.",
                "country_code": "US",
            },
        ],
        related_records=[],
        trace={"grounding_mode": "verified_local_corpus"},
    )

    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []
