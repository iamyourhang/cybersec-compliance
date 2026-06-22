from collector.document.chunker import extract_document_sections
from collector.document.retrieval_service import RetrievalService


def test_extract_document_sections_preserves_article_structure():
    sections = extract_document_sections(
        page_texts=[
            {
                "page_number": 1,
                "text": (
                    "Chapter I General Provisions\n"
                    "Article 1 Scope\n"
                    "This Regulation applies to connected products placed on the market.\n\n"
                    "Article 2 Essential requirements\n"
                    "Manufacturers shall ensure secure by default configurations."
                ),
            }
        ]
    )

    assert len(sections) >= 3
    assert sections[0]["section_type"] == "chapter"
    assert sections[0]["section_ref"] == "Chapter I"
    assert sections[1]["section_type"] == "article"
    assert sections[1]["section_ref"] == "Article 1"
    assert "Scope" in (sections[1]["title"] or "")
    assert "connected products" in sections[1]["content"]
    assert sections[2]["section_ref"] == "Article 2"


def test_extract_document_sections_skips_table_of_contents_pages():
    sections = extract_document_sections(
        page_texts=[
            {
                "page_number": 1,
                "text": (
                    "Table of Contents\n"
                    "Section 2.1: Access and Authorization .......... 12\n"
                    "Section 2.2: Vulnerability Handling ............ 17\n"
                    "Article 10 Essential requirements .............. 36\n"
                    "Annex I Conformity assessment .................. 90"
                ),
            }
        ]
    )

    assert sections == []


def test_extract_document_sections_skips_toc_page_but_keeps_body_sections():
    sections = extract_document_sections(
        page_texts=[
            {
                "page_number": 1,
                "text": (
                    "Table of Contents\n"
                    "Article 1 Scope ................................. 5\n"
                    "Article 2 Definitions .......................... 7\n"
                ),
            },
            {
                "page_number": 2,
                "text": (
                    "Chapter I General Provisions\n"
                    "Article 1 Scope\n"
                    "This Regulation applies to connected products placed on the market.\n"
                ),
            },
        ]
    )

    assert len(sections) == 2
    assert sections[0]["section_ref"] == "Chapter I"
    assert sections[1]["section_ref"] == "Article 1"
    assert "connected products" in sections[1]["content"]


def test_retrieval_service_prioritizes_clause_hits():
    from database.repository import ComplianceIndexRepository, ComplianceRepository

    class _FakeEmbedder:
        def embed_texts(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    class _FakeChunkRepo:
        @staticmethod
        def section_search(question, country_code=None, document_id=None, verified_only=False, limit=10):
            return [
                {
                    "document_id": "doc-1",
                    "document_name": "Cyber Resilience Act",
                    "chunk_index": 0,
                    "page_from": 12,
                    "page_to": 13,
                    "section_path": "Chapter II > Article 10",
                    "clause_ref": "Article 10",
                    "content": "Article 10 sets out the essential cybersecurity requirements.",
                    "country_code": "EU",
                    "compliance_id": None,
                    "section_score": 1.0,
                }
            ]

        @staticmethod
        def vector_search(query_vector, country_code=None, document_id=None, verified_only=False, limit=20):
            return [
                {
                    "document_id": "doc-2",
                    "document_name": "Other Regulation",
                    "chunk_index": 1,
                    "page_from": 2,
                    "page_to": 2,
                    "section_path": "Article 3",
                    "clause_ref": "Article 3",
                    "content": "General obligations for market surveillance authorities.",
                    "country_code": "EU",
                    "compliance_id": None,
                    "vector_score": 0.95,
                }
            ]

        @staticmethod
        def keyword_search(keyword, country_code=None, document_id=None, verified_only=False, limit=20):
            return []

    class _EmptySpecRepo:
        @staticmethod
        def search_for_rag(**kwargs):
            return []

    service = RetrievalService(
        embedder=_FakeEmbedder(),
        chunk_repository=_FakeChunkRepo,
        spec_repository=_EmptySpecRepo,
    )
    ComplianceRepository.list_by_country = staticmethod(lambda country_code: [])
    ComplianceIndexRepository.list_by_country = staticmethod(lambda country_code, verified_only=True, limit=5: [])

    result = service.retrieve("What does Article 10 require?", country_code="EU", top_k=3)

    assert result["hits"][0]["document_id"] == "doc-1"
    assert result["hits"][0]["clause_ref"] == "Article 10"
    assert result["trace"]["verified_only"] is True
