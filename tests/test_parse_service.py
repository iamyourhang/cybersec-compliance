from collector.document.parse_service import DocumentParseService
from collector.document import parse_service as parse_service_module
from collector.providers.base import LLMResponse


def test_parse_service_falls_back_when_ai_extract_fails(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "get",
        lambda doc_id: {
            "id": doc_id,
            "name": "CRA Firewall Draft",
            "country_code": "EU",
            "cos_key": "fake.pdf",
            "parse_status": "pending",
            "file_name": "fake.pdf",
        },
    )
    monkeypatch.setattr(parse_service_module.DocRepository, "set_parsing", lambda doc_id: None)
    monkeypatch.setattr(parse_service_module.DocRepository, "set_progress", lambda doc_id, progress, msg: None)
    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "set_parsed",
        lambda doc_id, result, compliance_id=None: captured.update(
            {"doc_id": doc_id, "result": result, "compliance_id": compliance_id}
        ),
    )
    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "set_failed",
        lambda doc_id, error: (_ for _ in ()).throw(AssertionError(error)),
    )
    monkeypatch.setattr(
        parse_service_module,
        "extract_page_texts_from_bytes",
        lambda pdf_bytes: (
            [
                {
                    "page_number": 1,
                    "text": "\n".join(
                        [
                            "Draft ETSI EN 304 636 V0.0.9",
                            "Cybersecurity requirements for firewalls",
                            "Date of Release: 2025-12-15",
                            "Effective Date: 2026-06-01",
                            "Issued by ETSI",
                            "This draft applies to firewall products, network security gateways, and related network devices.",
                            "The text is intentionally repeated to exceed the minimum text threshold for parse fallback validation.",
                            "This draft applies to firewall products, network security gateways, and related network devices.",
                            "The text is intentionally repeated to exceed the minimum text threshold for parse fallback validation.",
                            "This draft applies to firewall products, network security gateways, and related network devices.",
                        ]
                    ),
                }
            ]
        ),
    )

    class _FakeStorage:
        def download_bytes(self, cos_key):
            return b"%PDF-1.4"

    service = DocumentParseService(storage=_FakeStorage())
    service._router.chat = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("provider timeout"))

    result = service.parse_document("doc-1", write_to_knowledge=False)

    assert result["success"] is True
    assert result["entry"]["data_source"] == "document_parse_fallback"
    assert result["entry"]["entry_type"] == "standard"
    assert result["entry"]["country_code"] == "EU"
    assert result["entry"]["effective_date"].isoformat() == "2026-06-01"
    assert "firewall_utm" in result["entry"]["applicable_products"]
    assert captured["doc_id"] == "doc-1"


def test_parse_service_uses_channel_router(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "get",
        lambda doc_id: {
            "id": doc_id,
            "name": "CRA Firewall Draft",
            "country_code": "EU",
            "cos_key": "fake.pdf",
            "parse_status": "pending",
            "file_name": "fake.pdf",
        },
    )
    monkeypatch.setattr(parse_service_module.DocRepository, "set_parsing", lambda doc_id: None)
    monkeypatch.setattr(parse_service_module.DocRepository, "set_progress", lambda doc_id, progress, msg: None)
    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "set_parsed",
        lambda doc_id, result, compliance_id=None: captured.update(
            {"doc_id": doc_id, "result": result, "compliance_id": compliance_id}
        ),
    )
    monkeypatch.setattr(parse_service_module.DocRepository, "set_failed", lambda doc_id, error: None)
    monkeypatch.setattr(
        parse_service_module.CanonicalRequirementRepository,
        "upsert_parse_candidate",
        lambda doc, parsed: None,
    )
    monkeypatch.setattr(
        parse_service_module,
        "extract_page_texts_from_bytes",
        lambda pdf_bytes: [
            {
                "page_number": 1,
                "text": (
                    "Draft ETSI EN 304 636 V0.0.9\n"
                    "Cybersecurity requirements for firewalls\n"
                    "Issued by ETSI\n"
                    "Date of Release: 2025-12-15\n"
                    "Effective Date: 2026-06-01\n"
                    "This draft applies to firewall products and network devices. " * 4
                ),
            }
        ],
    )

    used = {}

    class _FakeRouter:
        def chat(self, **kwargs):
            used["called"] = True
            return LLMResponse(
                content='{"name":"CRA Firewall Draft","entry_type":"regulation","mandatory":"mandatory","status":"draft","country_code":"EU","issuing_body":"ETSI","technical_standards":[],"effective_date":"2026-06-01","transition_end_date":null,"published_date":"2025-12-15","applicable_products":["firewall_utm"],"scope_description":"scope","requirements":{"key_requirements":[],"assessment_route":null,"penalty":null,"special_notes":null},"testing_bodies":[],"assessment_procedure":null,"official_url":null,"remarks":"ok","confidence_score":90}',
                provider_name="fake",
                model="fake-model",
            )

    class _FakeStorage:
        def download_bytes(self, cos_key):
            return b"%PDF-1.4"

    service = DocumentParseService(storage=_FakeStorage(), router=_FakeRouter())

    result = service.parse_document("doc-1", write_to_knowledge=False)

    assert result["success"] is True
    assert used["called"] is True


def test_parse_service_preserves_existing_compliance_link(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "get",
        lambda doc_id: {
            "id": doc_id,
            "compliance_id": "existing-compliance-id",
            "name": "Cyber Trust Mark Program Final Rule",
            "country_code": "US",
            "cos_key": "official.pdf",
            "parse_status": "pending",
            "file_name": "official.pdf",
            "file_type": "pdf",
        },
    )
    monkeypatch.setattr(parse_service_module.DocRepository, "set_parsing", lambda doc_id: None)
    monkeypatch.setattr(parse_service_module.DocRepository, "set_progress", lambda doc_id, progress, msg: None)
    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "set_parsed",
        lambda doc_id, result, compliance_id=None: captured.update(
            {"doc_id": doc_id, "result": result, "compliance_id": compliance_id}
        ),
    )
    monkeypatch.setattr(parse_service_module.DocRepository, "set_failed", lambda doc_id, error: None)
    monkeypatch.setattr(
        parse_service_module.CanonicalRequirementRepository,
        "upsert_parse_candidate",
        lambda doc, parsed: (_ for _ in ()).throw(AssertionError("should not upsert candidate")),
    )
    monkeypatch.setattr(
        parse_service_module,
        "extract_page_texts_from_bytes",
        lambda pdf_bytes: [
            {
                "page_number": 1,
                "text": (
                    "Cyber Trust Mark Program Final Rule\n"
                    "Federal Communications Commission\n"
                    "This voluntary cybersecurity labeling program applies to consumer Internet of Things products. "
                    "The text is repeated to exceed the minimum extraction threshold. " * 4
                ),
            }
        ],
    )

    class _FakeRouter:
        def chat(self, **kwargs):
            return LLMResponse(
                content='{"name":"Cyber Trust Mark Program Final Rule","entry_type":"regulation","mandatory":"voluntary","status":"active","country_code":"US","issuing_body":"FCC","technical_standards":[],"effective_date":"2024-08-29","transition_end_date":null,"published_date":"2024-07-30","applicable_products":[],"scope_description":"scope","requirements":{"key_requirements":[],"assessment_route":null,"penalty":null,"special_notes":null},"testing_bodies":[],"assessment_procedure":null,"official_url":null,"remarks":"ok","confidence_score":90}',
                provider_name="fake",
                model="fake-model",
            )

    class _FakeStorage:
        def download_bytes(self, cos_key):
            return b"%PDF-1.4"

    service = DocumentParseService(storage=_FakeStorage(), router=_FakeRouter())

    result = service.parse_document("doc-linked", write_to_knowledge=False)

    assert result["success"] is True
    assert result["compliance_id"] == "existing-compliance-id"
    assert captured["compliance_id"] == "existing-compliance-id"


def test_parse_service_does_not_upsert_knowledge_when_write_to_knowledge_true(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "get",
        lambda doc_id: {
            "id": doc_id,
            "name": "CRA Firewall Draft",
            "country_code": "EU",
            "cos_key": "fake.pdf",
            "parse_status": "pending",
            "file_name": "fake.pdf",
        },
    )
    monkeypatch.setattr(parse_service_module.DocRepository, "set_parsing", lambda doc_id: None)
    monkeypatch.setattr(parse_service_module.DocRepository, "set_progress", lambda doc_id, progress, msg: None)
    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "set_parsed",
        lambda doc_id, result, compliance_id=None: captured.update(
            {"doc_id": doc_id, "result": result, "compliance_id": compliance_id}
        ),
    )
    monkeypatch.setattr(parse_service_module.DocRepository, "set_failed", lambda doc_id, error: None)
    monkeypatch.setattr(
        parse_service_module.CanonicalRequirementRepository,
        "upsert_parse_candidate",
        lambda doc, parsed: None,
    )
    monkeypatch.setattr(
        parse_service_module,
        "extract_page_texts_from_bytes",
        lambda pdf_bytes: [
            {
                "page_number": 1,
                "text": (
                    "Draft ETSI EN 304 636 V0.0.9\n"
                    "Cybersecurity requirements for firewalls\n"
                    "Issued by ETSI\n"
                    "Date of Release: 2025-12-15\n"
                    "Effective Date: 2026-06-01\n"
                    "This draft applies to firewall products and network devices. " * 4
                ),
            }
        ],
    )

    class _FakeRouter:
        def chat(self, **kwargs):
            return LLMResponse(
                content='{"name":"CRA Firewall Draft","entry_type":"regulation","mandatory":"mandatory","status":"draft","country_code":"EU","issuing_body":"ETSI","technical_standards":[],"effective_date":"2026-06-01","transition_end_date":null,"published_date":"2025-12-15","applicable_products":["firewall_utm"],"scope_description":"scope","requirements":{"key_requirements":[],"assessment_route":null,"penalty":null,"special_notes":null},"testing_bodies":[],"assessment_procedure":null,"official_url":null,"remarks":"ok","confidence_score":90}',
                provider_name="fake",
                model="fake-model",
            )

    class _FakeStorage:
        def download_bytes(self, cos_key):
            return b"%PDF-1.4"

    service = DocumentParseService(storage=_FakeStorage(), router=_FakeRouter())
    service._upsert_knowledge = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not write knowledge"))

    result = service.parse_document("doc-1", write_to_knowledge=True)

    assert result["success"] is True
    assert captured["compliance_id"] is None


def test_parse_service_supports_html_documents(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "get",
        lambda doc_id: {
            "id": doc_id,
            "name": "IoT Secure by Design",
            "country_code": "AU",
            "cos_key": "official.html",
            "parse_status": "pending",
            "file_name": "official.html",
            "file_type": "html",
        },
    )
    monkeypatch.setattr(parse_service_module.DocRepository, "set_parsing", lambda doc_id: None)
    monkeypatch.setattr(parse_service_module.DocRepository, "set_progress", lambda doc_id, progress, msg: None)
    monkeypatch.setattr(
        parse_service_module.DocRepository,
        "set_parsed",
        lambda doc_id, result, compliance_id=None: captured.update(
            {"doc_id": doc_id, "result": result, "compliance_id": compliance_id}
        ),
    )
    monkeypatch.setattr(parse_service_module.DocRepository, "set_failed", lambda doc_id, error: None)
    monkeypatch.setattr(
        parse_service_module.CanonicalRequirementRepository,
        "upsert_parse_candidate",
        lambda doc, parsed: None,
    )

    class _FakeRouter:
        def chat(self, **kwargs):
            return LLMResponse(
                content='{"name":"IoT Secure by Design","entry_type":"standard","mandatory":"recommended","status":"active","country_code":"AU","issuing_body":"Cyber.gov.au","technical_standards":[],"effective_date":null,"transition_end_date":null,"published_date":"2023-09-01","applicable_products":["wireless_ap"],"scope_description":"scope","requirements":{"key_requirements":[],"assessment_route":null,"penalty":null,"special_notes":null},"testing_bodies":[],"assessment_procedure":null,"official_url":null,"remarks":"ok","confidence_score":90}',
                provider_name="fake",
                model="fake-model",
            )

    class _FakeStorage:
        def download_bytes(self, cos_key):
            paragraphs = [
                "This guidance applies to smart devices, home routers, and wireless access points.",
                "Manufacturers should implement secure defaults and unique credentials for every device.",
                "Manufacturers should provide coordinated vulnerability disclosure and secure software updates.",
                "The document explains communication security, software integrity, and telemetry protections.",
            ]
            return (
                b"<html><body><h1>IoT Secure by Design</h1>"
                + "".join(f"<p>{item}</p>" for item in paragraphs).encode("utf-8")
                + b"</body></html>"
            )

    service = DocumentParseService(storage=_FakeStorage(), router=_FakeRouter())
    result = service.parse_document("doc-html", write_to_knowledge=False)

    assert result["success"] is True
    assert captured["doc_id"] == "doc-html"
