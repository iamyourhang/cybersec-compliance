from collector.audit.authenticity import assess_record_authenticity
from scripts.authenticity_audit import determine_final_review


def test_authenticity_quarantine_mapping_for_critical_entry():
    verdict = assess_record_authenticity(
        {
            "name": "Voluntary Cybersecurity Excellence Label for Network Devices",
            "entry_type": "certification",
            "official_url": None,
            "verified": False,
            "confidence_score": 60,
            "data_source": "volcengine_primary/doubao-seed-2-0-pro-260215",
        }
    )

    assert verdict["risk_level"] == "critical"
    assert verdict["recommended_action"] == "quarantine"


def test_determine_final_review_marks_authoritative_match_verified():
    result = determine_final_review(
        {
            "name": "Directive (EU) 2022/2555 of the European Parliament and of the Council on measures for a high common level of cybersecurity across the Union",
            "entry_type": "regulation",
            "official_url": "https://eur-lex.europa.eu/eli/dir/2022/2555/oj",
            "verified": False,
            "confidence_score": 70,
            "data_source": "official_source:EUR-Lex",
        }
    )

    assert result["authenticity_status"] == "verified"
    assert result["risk_score"] == 0
    assert result["reasons"] == ["authoritative_link_match"]


def test_determine_final_review_demotes_low_risk_candidate_to_suspicious():
    result = determine_final_review(
        {
            "name": "IEC 62443-3-3:2019 Security for industrial automation and control systems",
            "entry_type": "standard",
            "official_url": None,
            "verified": False,
            "confidence_score": 78,
            "data_source": "volcengine_primary/doubao-seed-2-0-pro-260215",
        }
    )

    assert result["authenticity_status"] == "suspicious"
    assert result["risk_score"] >= 0


def test_determine_final_review_keeps_verified_flag_as_verified():
    result = determine_final_review(
        {
            "name": "Information Security Early Warning Partnership Guideline",
            "entry_type": "regulation",
            "official_url": None,
            "verified": True,
            "confidence_score": 98,
            "data_source": "document_parse",
        }
    )

    assert result["authenticity_status"] == "verified"
    assert result["reasons"] == ["verified_flag_present"]
