from scripts.seed_country_research_outcomes import RESEARCHED_NO_SPECIFIC_SOURCE


def test_no_specific_source_outcomes_are_explicit_and_country_scoped():
    outcomes = {item["country_code"]: item for item in RESEARCHED_NO_SPECIFIC_SOURCE}

    assert {"KP", "FM", "VA", "DM", "HT", "CF", "ER", "GQ", "GW", "KM"} <= set(outcomes)
    assert all("2026-05-09" in item["review_note"] for item in outcomes.values())
    assert all("未定位" in item["review_note"] or "未发现" in item["review_note"] for item in outcomes.values())
