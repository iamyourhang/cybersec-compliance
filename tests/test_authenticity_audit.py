from collector.audit.authenticity import assess_record_authenticity, classify_probe_result, probe_official_url


def test_assess_record_authenticity_flags_template_like_ai_entry():
    result = assess_record_authenticity(
        {
            "name": "National Cybersecurity Certification Scheme for Network and Telecommunications Equipment",
            "entry_type": "certification",
            "official_url": None,
            "verified": False,
            "confidence_score": 60,
            "data_source": "volcengine_primary/doubao-seed-2-0-pro-260215",
        }
    )

    assert result["risk_level"] in {"high", "critical"}
    assert result["risk_score"] >= 70
    assert "missing_official_url" in result["reasons"]
    assert "template_like_name" in result["reasons"]
    assert result["recommended_action"] == "quarantine"


def test_assess_record_authenticity_keeps_verified_human_record_low_risk():
    result = assess_record_authenticity(
        {
            "name": "UK Product Security and Telecommunications Infrastructure Act (PSTI Act)",
            "entry_type": "regulation",
            "official_url": "https://www.legislation.gov.uk/ukpga/2022/46",
            "verified": True,
            "confidence_score": 98,
            "data_source": "human",
        }
    )

    assert result["risk_level"] == "low"
    assert result["risk_score"] < 25
    assert result["recommended_action"] == "keep"


def test_classify_probe_result_marks_not_found_as_critical_signal():
    result = classify_probe_result(
        {
            "ok": False,
            "status_code": 404,
            "error": None,
            "final_url": "https://example.com/missing",
        }
    )

    assert result["risk_delta"] >= 30
    assert result["reason"] == "official_url_not_found"


def test_probe_official_url_handles_timeout_errors(monkeypatch):
    class _TimeoutOpener:
        def open(self, request, timeout=20):
            raise TimeoutError("The read operation timed out")

    monkeypatch.setattr("collector.audit.authenticity.build_opener", lambda *args, **kwargs: _TimeoutOpener())

    result = probe_official_url("https://example.com/slow")

    assert result["ok"] is False
    assert result["status_code"] is None
    assert result["final_url"] is None
    assert "timed out" in result["error"]
