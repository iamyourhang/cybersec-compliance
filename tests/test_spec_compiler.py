from collector.document.spec_compiler import (
    ClauseExtractor,
    RequirementCompiler,
    SpecVerifier,
    compile_rule_level_specs,
)


def test_clause_extractor_detects_red_article_3_requirements():
    chunks = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "page_from": 2,
            "page_to": 2,
            "content": (
                "Article 3(3), point (d), Article 3(3), point (e), "
                "and Article 3(3), point (f) shall apply to internet-connected radio equipment."
            ),
        }
    ]

    evidence = ClauseExtractor(chunks).extract()

    assert [item.rule_id for item in evidence] == ["NET-RED-001", "ENC-RED-001", "AUTH-RED-001"]
    assert all(item.source_pages == "2" for item in evidence)
    assert all(item.source_chunk_ids == ["11111111-1111-1111-1111-111111111111"] for item in evidence)


def test_requirement_compiler_emits_traceable_specs_from_evidence():
    chunks = [
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
    ]

    evidence = ClauseExtractor(chunks).extract()
    specs = RequirementCompiler(["home_router", "wireless_ap"]).compile(evidence)

    assert [spec["req_id"] for spec in specs] == ["CMP-FCC-001", "CMP-FCC-002", "UPD-FCC-001"]
    assert all(spec["source_pages"] == "88-89" for spec in specs)
    assert all(spec["source_chunk_ids"] == ["22222222-2222-2222-2222-222222222222"] for spec in specs)
    assert all(spec["verification_method_zh"] for spec in specs)


def test_spec_verifier_drops_specs_without_traceable_source():
    specs = [
        {
            "req_id": "GOOD-001",
            "module_zh": "安全更新与补丁管理",
            "description_zh": "产品必须支持安全更新。",
            "regulation_clause": "Annex I",
        },
        {
            "req_id": "BAD-001",
            "module_zh": "安全更新与补丁管理",
            "description_zh": "产品必须支持安全更新。",
        },
    ]

    assert [spec["req_id"] for spec in SpecVerifier().filter_valid(specs)] == ["GOOD-001"]


def test_compile_rule_level_specs_reads_chunks_from_repository(monkeypatch):
    monkeypatch.setattr(
        "collector.document.spec_compiler.RegulationChunkRepository.list_by_document",
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

    specs = compile_rule_level_specs("doc-cra", "EU", ["software"])

    req_ids = [spec["req_id"] for spec in specs]
    assert "CFG-CRA-001" in req_ids
    assert "UPD-CRA-001" in req_ids
    assert "VUL-CRA-001" in req_ids
    assert "VUL-CRA-002" in req_ids
    assert all(spec["source_chunk_ids"] for spec in specs)
