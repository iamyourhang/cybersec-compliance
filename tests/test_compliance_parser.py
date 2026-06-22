from collector.parsers.compliance_parser import normalize_entry


def test_normalize_entry_maps_policy_and_strategy_plan_to_standard():
    base = {
        "name": "National Cybersecurity Plan",
        "mandatory": "recommended",
        "country_code": "PH",
    }

    assert normalize_entry({**base, "entry_type": "policy"})["entry_type"] == "standard"
    assert normalize_entry({**base, "entry_type": "strategy_plan"})["entry_type"] == "standard"
