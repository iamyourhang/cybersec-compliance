import sys
import types
from concurrent.futures import TimeoutError as FuturesTimeoutError


def test_generate_from_doc_stores_spec_requirements_and_count(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.DocRepository.get",
        lambda doc_id: {
            "id": doc_id,
            "name": "Cyber Resilience Act",
            "country_code": "EU",
            "cos_key": "reports/documents/EU/cra.pdf",
            "compliance_id": "rec-1",
        },
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.extract_text_from_bytes",
        lambda pdf_bytes: ("Article 10 Connected products shall be secure." * 20, 12),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.generate_spec_excel",
        lambda specs, regulation_name, country_code: b"fake-xlsx",
    )

    stored = {}
    monkeypatch.setattr(
        "collector.document.spec_generator.RegulationSpecRequirementRepository.upsert_many",
        lambda rows: stored.update({"rows": rows}) or len(rows),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.DocRepository.set_spec_generated",
        lambda doc_id, cos_url, cos_key, stored_count: stored.update(
            {
                "doc_id": doc_id,
                "cos_url": cos_url,
                "cos_key": cos_key,
                "stored_count": stored_count,
            }
        ),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.DocRepository.set_spec_progress",
        lambda doc_id, progress, msg: None,
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: type(
            "_FakeCos",
            (),
            {
                "download_bytes": lambda self, key: b"%PDF-1.4\nfake",
                "upload_bytes": lambda self, data, cos_key: f"https://cos.example.com/{cos_key}",
            },
        )(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    service = SpecGeneratorService()
    service._extract_specs = lambda text, regulation_name, country_code, products, doc_id=None: [
        {
            "req_id": "AUTH-001",
            "module_zh": "身份认证与密码管理",
            "module_en": "Authentication",
            "title_zh": "默认密码修改",
            "title_en": "Change default password",
            "description_zh": "首次登录必须强制修改默认密码。",
            "description_en": "Force password change on first login.",
            "applicable_products": ["home_router"],
            "mandatory": "mandatory",
            "priority": "P1",
            "regulation_clause": "Article 10",
            "verification_method_zh": "验证首次登录流程",
            "verification_method_en": "Verify first-login flow",
            "notes_zh": "无",
            "notes_en": "None",
        },
        {
            "req_id": "UPD-001",
            "module_zh": "安全更新与补丁管理",
            "module_en": "Updates",
            "title_zh": "安全更新机制",
            "title_en": "Security update mechanism",
            "description_zh": "设备必须提供安全更新机制。",
            "description_en": "Provide a secure update mechanism.",
            "applicable_products": ["home_router", "firewall_utm"],
            "mandatory": "mandatory",
            "priority": "P1",
            "regulation_clause": "Annex I",
            "verification_method_zh": "验证更新签名校验",
            "verification_method_en": "Verify signature validation",
            "notes_zh": "支持在线更新",
            "notes_en": "Online updates supported",
        },
    ]

    result = service.generate_from_doc("doc-1")

    assert result["spec_count"] == 2
    assert result["stored_count"] == 2
    assert stored["stored_count"] == 2
    assert stored["rows"][0]["document_id"] == "doc-1"
    assert stored["rows"][0]["compliance_id"] == "rec-1"
    assert stored["rows"][0]["regulation_clause"] == "Article 10"


def test_generate_from_html_doc_uses_html_extractor(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.DocRepository.get",
        lambda doc_id: {
            "id": doc_id,
            "name": "IoT Secure by Design",
            "country_code": "AU",
            "cos_key": "reports/documents/AU/official.html",
            "file_type": "html",
            "compliance_id": "rec-html",
        },
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.extract_text_from_html_bytes",
        lambda html_bytes: ("Manufacturers must provide secure updates." * 20, 1),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.generate_spec_excel",
        lambda specs, regulation_name, country_code: b"fake-xlsx",
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.RegulationSpecRequirementRepository.upsert_many",
        lambda rows: len(rows),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.DocRepository.set_spec_generated",
        lambda doc_id, cos_url, cos_key, stored_count: None,
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.DocRepository.set_spec_progress",
        lambda doc_id, progress, msg: None,
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: type(
            "_FakeCos",
            (),
            {
                "download_bytes": lambda self, key: b"<html></html>",
                "upload_bytes": lambda self, data, cos_key: f"https://cos.example.com/{cos_key}",
            },
        )(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    service = SpecGeneratorService()
    service._extract_specs = lambda text, regulation_name, country_code, products, doc_id=None: [
        {
            "req_id": "UPD-001",
            "module_zh": "安全更新与补丁管理",
            "description_zh": "设备必须提供安全更新机制。",
            "applicable_products": ["wireless_ap"],
            "mandatory": "mandatory",
            "priority": "P1",
            "regulation_clause": "Guidance section 2",
        }
    ]

    result = service.generate_from_doc("doc-html")

    assert result["spec_count"] == 1
    assert result["stored_count"] == 1


def test_extract_specs_window_retries_with_smaller_prompt_after_timeout(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )

    service = SpecGeneratorService()
    calls = []

    def fake_call(prompt, max_tokens):
        calls.append({"prompt_len": len(prompt), "max_tokens": max_tokens})
        if len(calls) == 1:
            raise FuturesTimeoutError()
        return type("_Resp", (), {"content": '[{"req_id":"REQ-1","module_zh":"模块","description_zh":"说明"}]'})()

    monkeypatch.setattr(service, "_call_spec_model", fake_call)

    specs = service._extract_specs_from_window(
        window_text="A" * 60000,
        regulation_name="CRA",
        country_code="EU",
        products=["firewall_utm"],
        window_index=1,
        total_windows=1,
    )

    assert len(specs) == 1
    assert len(calls) == 2
    assert calls[0]["max_tokens"] > calls[1]["max_tokens"]
    assert calls[0]["prompt_len"] > calls[1]["prompt_len"]


def test_extract_specs_walks_full_text_windows_and_merges(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService, SPEC_WINDOW_CHARS

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )

    service = SpecGeneratorService()
    window_calls = []

    def fake_extract_window(window_text, regulation_name, country_code, products, window_index, total_windows):
        window_calls.append((window_index, total_windows, len(window_text)))
        return [{
            "req_id": f"REQ-{window_index}",
            "module_zh": "模块",
            "description_zh": f"说明 {window_index}",
            "regulation_clause": f"Article {window_index}",
        }]

    merge_inputs = {}

    def fake_merge(regulation_name, country_code, products, candidate_specs):
        merge_inputs["count"] = len(candidate_specs)
        return candidate_specs[:2]

    monkeypatch.setattr(service, "_extract_specs_from_window", fake_extract_window)
    monkeypatch.setattr(service, "_merge_specs", fake_merge)

    text = "A" * (SPEC_WINDOW_CHARS * 2 + 5000)
    specs = service._extract_specs(text, "CRA", "EU", ["firewall_utm"])

    assert len(window_calls) >= 2
    assert merge_inputs["count"] == len(window_calls)
    assert len(specs) == 2


def test_extract_specs_prefers_sections_over_raw_text(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.RegulationSectionRepository.list_by_document",
        lambda doc_id, limit=5000: [
            {
                "section_ref": "Article 1",
                "title": "Scope",
                "section_path": "Chapter I > Article 1",
                "content": "This Regulation applies to connected products.",
            },
            {
                "section_ref": "Article 2",
                "title": "Security requirements",
                "section_path": "Chapter I > Article 2",
                "content": "Manufacturers shall provide secure updates.",
            },
        ],
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.RegulationChunkRepository.list_by_document",
        lambda doc_id, limit=5000: [],
    )

    service = SpecGeneratorService()
    windows = service._build_extraction_windows("doc-1", "fallback raw text")

    assert len(windows) == 1
    assert "Article 1" in windows[0]
    assert "Manufacturers shall provide secure updates." in windows[0]


def test_structured_spec_windows_split_oversized_single_section(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService, SPEC_STRUCTURED_WINDOW_CHARS

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.RegulationSectionRepository.list_by_document",
        lambda doc_id, limit=5000: [
            {
                "section_ref": "Article 13",
                "title": "Obligations of manufacturers",
                "section_path": "Chapter II > Article 13",
                "content": "Manufacturers shall ensure cybersecurity. "
                * (SPEC_STRUCTURED_WINDOW_CHARS // 40 + 3),
            }
        ],
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.RegulationChunkRepository.list_by_document",
        lambda doc_id, limit=5000: [],
    )

    service = SpecGeneratorService()
    windows = service._build_extraction_windows("doc-1", "fallback raw text")

    assert len(windows) >= 2
    assert all(len(window) <= SPEC_STRUCTURED_WINDOW_CHARS + 500 for window in windows)
    assert all("Article 13" in window for window in windows)


def test_spec_model_call_uses_single_short_provider_attempt(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document import spec_generator as spec_module
    from collector.document.spec_generator import SpecGeneratorService
    from collector.providers.base import LLMResponse

    captured = {}

    class _FakeRouter:
        def chat(self, **kwargs):
            captured.update(kwargs)
            return LLMResponse(content="[]", provider_name="fake", model="fake")

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: _FakeRouter(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )

    service = SpecGeneratorService()
    service._call_spec_model("prompt", 1200)

    assert captured["timeout"] == spec_module.SPEC_MODEL_TIMEOUT_SECONDS
    assert captured["max_retries"] == 1


def test_rule_level_fallback_extracts_red_article_3_requirements(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.RegulationChunkRepository.list_by_document",
        lambda doc_id, limit=5000: [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "page_from": 2,
                "page_to": 2,
                "content": (
                    "Article 3(3), point (d), Article 3(3), point (e), "
                    "and Article 3(3), point (f) shall apply to internet-connected radio equipment."
                ),
            }
        ],
    )

    service = SpecGeneratorService()
    specs = service._build_rule_level_fallback_specs(
        "doc-red",
        "EU",
        ["home_router", "wireless_ap"],
    )

    assert [spec["req_id"] for spec in specs] == ["NET-RED-001", "ENC-RED-001", "AUTH-RED-001"]
    assert all(spec["source_pages"] == "2" for spec in specs)
    assert all(spec["source_chunk_ids"] == ["11111111-1111-1111-1111-111111111111"] for spec in specs)


def test_rule_level_fallback_extracts_cyber_trust_mark_requirements(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.RegulationChunkRepository.list_by_document",
        lambda doc_id, limit=5000: [
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "page_from": 88,
                "page_to": 89,
                "content": (
                    "§ 8.220(c)(3) the CLA shall accept test data from an accredited CyberLAB. "
                    "§ 8.220(g) post-market surveillance requires product sampling and notice of non-compliance. "
                    "§ 8.222(b) registry information includes secure updates, default password changes, "
                    "minimum support period, SBOM and HBOM disclosure."
                ),
            }
        ],
    )

    service = SpecGeneratorService()
    specs = service._build_rule_level_fallback_specs(
        "doc-us",
        "US",
        ["home_router", "wireless_ap"],
    )

    assert [spec["req_id"] for spec in specs] == ["CMP-FCC-001", "CMP-FCC-002", "UPD-FCC-001"]
    assert all(spec["source_pages"] == "88-89" for spec in specs)


def test_rule_level_fallback_extracts_cra_annex_and_reporting_requirements(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.RegulationChunkRepository.list_by_document",
        lambda doc_id, limit=5000: [
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "page_from": 61,
                "page_to": 62,
                "content": (
                    "ANNEX I ESSENTIAL CYBERSECURITY REQUIREMENTS. Products shall be made available "
                    "without known exploitable vulnerabilities, with a secure by default configuration, "
                    "and vulnerabilities can be addressed through security updates including automatic security updates. "
                    "Part II Vulnerability handling requirements include drawing up a software bill of materials."
                ),
            },
            {
                "id": "44444444-4444-4444-4444-444444444444",
                "page_from": 18,
                "page_to": 18,
                "content": (
                    "Article 14 Reporting obligations. Early warning notification of an actively exploited "
                    "vulnerability without undue delay and in any event within 24 hours."
                ),
            },
        ],
    )

    service = SpecGeneratorService()
    specs = service._build_rule_level_fallback_specs("doc-cra", "EU", ["software"])

    req_ids = [spec["req_id"] for spec in specs]
    assert "CFG-CRA-001" in req_ids
    assert "UPD-CRA-001" in req_ids
    assert "VUL-CRA-001" in req_ids
    assert "VUL-CRA-002" in req_ids


def test_parse_specs_response_salvages_complete_objects_from_truncated_json(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )

    service = SpecGeneratorService()
    specs = service._parse_specs_response(
        """
        [
          {
            "req_id": "ENC-001",
            "module_zh": "数据加密与传输安全",
            "description_zh": "设备必须保护通信链路。",
            "regulation_clause": "§ 8.222"
          },
          {
            "req_id": "BROKEN",
            "module_zh": "日志与审计",
        """
    )

    assert len(specs) == 1
    assert specs[0]["req_id"] == "ENC-001"


def test_extract_specs_window_skips_unparseable_json_after_retries(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )

    service = SpecGeneratorService()
    monkeypatch.setattr(
        service,
        "_call_spec_model",
        lambda prompt, max_tokens: type("_Resp", (), {"content": '[{"req_id":"BROKEN"'})(),
    )

    specs = service._extract_specs_from_window(
        window_text="short text",
        regulation_name="Cyber Trust Mark",
        country_code="US",
        products=["home_router"],
        window_index=1,
        total_windows=1,
    )

    assert specs == []


def test_extract_specs_window_splits_on_repeated_timeout(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )

    service = SpecGeneratorService()
    call_counter = {"count": 0}

    def fake_call(prompt, max_tokens):
        call_counter["count"] += 1
        if call_counter["count"] <= 2:
            raise FuturesTimeoutError()
        return type("_Resp", (), {"content": '[{"req_id":"REQ-1","module_zh":"模块","description_zh":"说明","regulation_clause":"Article 1"}]'})()

    monkeypatch.setattr(service, "_call_spec_model", fake_call)

    specs = service._extract_specs_from_window(
        window_text="A" * 20000,
        regulation_name="CRA",
        country_code="EU",
        products=["firewall_utm"],
        window_index=1,
        total_windows=1,
    )

    assert len(specs) >= 1
    assert call_counter["count"] >= 3


def test_extract_specs_uses_rule_level_fallback_for_large_documents(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )

    service = SpecGeneratorService()
    monkeypatch.setattr(service, "_build_extraction_windows", lambda doc_id, text: ["x"] * 120)
    monkeypatch.setattr(
        service,
        "_build_rule_level_fallback_specs",
        lambda doc_id, country_code, products: [
            {
                "req_id": "CMP-FCC-001",
                "module_zh": "合规认证与测试",
                "description_zh": "测试数据要求",
                "regulation_clause": "§ 8.220(c)(3)",
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "_extract_specs_from_window",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not call model windows")),
    )

    specs = service._extract_specs("long", "Cyber Trust Mark", "US", ["home_router"], doc_id="doc-us")

    assert specs[0]["req_id"] == "CMP-FCC-001"


def test_extract_specs_uses_generic_chunk_fallback_for_large_documents_without_template_hits(monkeypatch):
    if "openpyxl" not in sys.modules:
        sys.modules["openpyxl"] = types.ModuleType("openpyxl")

    from collector.document.spec_generator import SpecGeneratorService

    monkeypatch.setattr(
        "collector.document.spec_generator.get_channel_router",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.CosStorage",
        lambda: object(),
    )
    monkeypatch.setattr(
        "collector.document.spec_generator.RegulationChunkRepository.list_by_document",
        lambda doc_id, limit=5000: [
            {
                "id": "55555555-5555-5555-5555-555555555555",
                "page_from": 12,
                "page_to": 13,
                "clause_ref": "Article 55",
                "content": "Manufacturers shall establish a vulnerability handling process and provide security updates.",
            }
        ],
    )

    service = SpecGeneratorService()
    monkeypatch.setattr(service, "_build_extraction_windows", lambda doc_id, text: ["x"] * 120)
    monkeypatch.setattr(service, "_build_rule_level_fallback_specs", lambda doc_id, country_code, products: [])
    monkeypatch.setattr(
        service,
        "_extract_specs_from_window",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not call model windows")),
    )

    specs = service._extract_specs("long", "Cybersecurity Act", "EU", ["software"], doc_id="doc-long")

    assert len(specs) == 1
    assert specs[0]["req_id"].startswith("GEN-EU-")
    assert specs[0]["regulation_clause"] == "Article 55"
    assert specs[0]["source_pages"] == "12-13"
    assert specs[0]["source_chunk_ids"] == ["55555555-5555-5555-5555-555555555555"]
