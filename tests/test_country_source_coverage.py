import re

from scripts.refresh_country_source_coverage import PRODUCT_REGIME_PATTERN, classify_product_coverage


def test_product_coverage_prefers_product_regime_when_product_records_exist():
    status, next_action = classify_product_coverage(
        verified_record_count=3,
        product_verified_count=1,
        coverage_status="verified_records_available",
    )

    assert status == "product_regime_verified"
    assert "产品级" in next_action


def test_product_coverage_marks_general_law_when_verified_but_no_product_regime():
    status, next_action = classify_product_coverage(
        verified_record_count=2,
        product_verified_count=0,
        coverage_status="verified_records_available",
    )

    assert status == "general_cyber_law_verified"
    assert "继续查找产品" in next_action


def test_product_coverage_preserves_no_product_regime_even_with_general_laws():
    status, next_action = classify_product_coverage(
        verified_record_count=2,
        product_verified_count=0,
        coverage_status="verified_records_available",
        product_research_status="no_product_regime_found_verified",
    )

    assert status == "no_product_regime_found_verified"
    assert "未发现独立产品级" in next_action


def test_product_coverage_preserves_no_product_regime_research_result():
    status, next_action = classify_product_coverage(
        verified_record_count=0,
        product_verified_count=0,
        coverage_status="researched_no_specific_source",
    )

    assert status == "no_product_regime_found_verified"
    assert "定期复核" in next_action


def test_product_coverage_pending_until_country_is_researched():
    status, next_action = classify_product_coverage(
        verified_record_count=0,
        product_verified_count=0,
        coverage_status="official_sources_seeded",
    )

    assert status == "pending_source_research"
    assert "补官方证据" in next_action


def test_product_regime_pattern_covers_labels_and_technical_regulations():
    pattern = re.compile(PRODUCT_REGIME_PATTERN)

    assert pattern.search("U.S. Cyber Trust Mark Program".lower())
    assert pattern.search("National Technical Regulation on minimum cybersecurity requirements".lower())
    assert pattern.search("Cyber Essentials certification".lower())
