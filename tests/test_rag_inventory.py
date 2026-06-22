from collector.document.rag_service import AskPayload, RAGService
from database.repository import ComplianceIndexRepository


class _NoRetrievalForInventory:
    def _infer_country_code(self, question):
        return "US"

    def _infer_product_code(self, question):
        return None

    def retrieve(self, **kwargs):
        raise AssertionError("inventory questions should use verified read model before chunk RAG")


def test_rag_answers_verified_inventory_questions_from_read_model(monkeypatch):
    captured = {}

    def list_filtered(**kwargs):
        captured.update(kwargs)
        return {
            "total": 2,
            "items": [
                {
                    "compliance_id": "record-1",
                    "document_id": "doc-1",
                    "country_code": "US",
                    "name": "Cyber Trust Mark Program Final Rule",
                    "entry_type": "regulation",
                    "mandatory": "mandatory",
                    "issuing_body": "FCC",
                    "official_url": "https://public-inspection.federalregister.gov/2024-14148.pdf",
                    "summary": "FCC 产品网络安全标签计划最终规则。",
                    "applicable_products": [],
                    "effective_date": None,
                },
                {
                    "compliance_id": "record-2",
                    "document_id": "doc-2",
                    "country_code": "US",
                    "name": "US NIAP Common Criteria Evaluation and Validation Scheme",
                    "entry_type": "certification",
                    "mandatory": "recommended",
                    "issuing_body": "NIAP",
                    "official_url": "https://www.commoncriteriaportal.org/cc/",
                    "summary": "IT 产品 Common Criteria 评估验证。",
                    "applicable_products": ["security_gateway"],
                    "effective_date": None,
                },
            ],
        }

    monkeypatch.setattr(ComplianceIndexRepository, "list_filtered", staticmethod(list_filtered))

    result = RAGService(retrieval_service=_NoRetrievalForInventory()).ask(
        AskPayload(
            question="美国 当前已验证的产品网络安全法规、认证和标准有哪些？请按强制/自愿分类，并给出依据。",
            verified_only=True,
        )
    )

    assert result["status"] == "answered"
    assert "强制" in result["answer"]
    assert "自愿/推荐" in result["answer"]
    assert "Cyber Trust Mark Program Final Rule" in result["answer"]
    assert "US NIAP Common Criteria Evaluation and Validation Scheme" in result["answer"]
    assert captured["country_code"] == "US"
    assert captured["authenticity_status"] == "verified"
    assert captured["include_suspicious"] is False
    assert len(result["citations"]) == 2
