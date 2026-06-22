from concurrent.futures import TimeoutError as FuturesTimeoutError

from collector.review.service import AuthenticityReviewService


def test_generate_ai_assist_falls_back_when_llm_times_out(monkeypatch):
    monkeypatch.setattr(
        "collector.review.service.ReviewCaseRepository.get_by_id",
        lambda case_id: {
            "id": case_id,
            "compliance_id": "rec-1",
            "current_status": "suspicious",
            "risk_score": 20,
            "reasons": ["official_scheme_confirmed"],
            "evidence_note": "已有官方项目线索，但缺少稳定 PDF。",
            "source_download_status": "failed",
        },
    )
    monkeypatch.setattr(
        "collector.review.service.ComplianceRepository.get_by_id",
        lambda record_id: {
            "id": record_id,
            "name": "Singapore Common Criteria Scheme (SCCS)",
            "country_code": "SG",
            "entry_type": "certification",
            "official_url": "https://www.csa.gov.sg/our-programmes/...",
        },
    )

    service = AuthenticityReviewService(router=object())
    monkeypatch.setattr(
        service,
        "get_evidence",
        lambda entity_id: {
            "entity_id": entity_id,
            "artifacts": [],
            "events": [],
        },
    )
    monkeypatch.setattr(
        service,
        "_call_ai_assist_model",
        lambda prompt: (_ for _ in ()).throw(FuturesTimeoutError()),
    )

    result = service.generate_ai_assist("case-1")

    assert result["case_id"] == "case-1"
    assert result["warning"]
    assert result["recommended_actions"]


def test_dry_run_authenticity_verification_only_returns_suggestions(monkeypatch):
    sample = [
        {
            "compliance_id": "rec-1",
            "country_code": "EU",
            "name": "ETSI EN 303 984 V1.1.1 Cyber Security for 5G Networking Equipment",
            "entry_type": "standard",
            "mandatory": "mandatory",
            "official_url": "https://www.etsi.org/example.pdf",
            "summary": "5G network equipment baseline requirements",
        },
        {
            "compliance_id": "rec-2",
            "country_code": "JP",
            "name": "JISEC-Certified Products[Software]",
            "entry_type": "certification",
            "mandatory": "voluntary",
            "official_url": "https://www.ipa.go.jp/en/security/jisec/software/certified-cert/index.html",
            "summary": None,
        },
    ]
    monkeypatch.setattr(
        "collector.review.service.ComplianceIndexRepository.list_for_verification",
        lambda **kwargs: sample,
    )

    class _Verifier:
        calls = []

        def verify(self, record):
            self.calls.append(record)
            return {
                "suggested_status": "quarantined" if record["country_code"] == "EU" else "suspicious",
                "official_evidence_found": record["country_code"] == "JP",
                "official_url": record.get("official_url"),
                "artifact_url": record.get("official_url"),
                "evidence_summary": "dry-run suggestion",
                "gaps": ["requires human confirmation"],
                "confidence": 0.8,
                "web_actions": [{"type": "search"}],
                "latency_ms": 123,
            }

    service = AuthenticityReviewService(router=object(), verification_agent=_Verifier())

    result = service.dry_run_authenticity_verification(current_status="suspicious", limit=2)

    assert result["dry_run"] is True
    assert result["sample_size"] == 2
    assert result["status_counts"] == {"quarantined": 1, "suspicious": 1}
    assert result["items"][0]["compliance_id"] == "rec-1"
    assert result["items"][0]["suggestion"]["suggested_status"] == "quarantined"
