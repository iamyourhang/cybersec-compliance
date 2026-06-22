from scripts.country_catalog import FULL_COUNTRY_CATALOG, region_for_code


def test_full_country_catalog_has_expected_global_target_size_and_no_duplicates():
    codes = [item["code"] for item in FULL_COUNTRY_CATALOG]

    assert len(codes) == 199
    assert len(codes) == len(set(codes))


def test_full_country_catalog_includes_un_observers_and_key_separate_markets():
    codes = {item["code"] for item in FULL_COUNTRY_CATALOG}

    assert {"PS", "VA", "TW", "HK", "XK", "EU"} <= codes


def test_full_country_catalog_includes_previous_gap_countries():
    codes = {item["code"] for item in FULL_COUNTRY_CATALOG}

    assert {"GT", "IQ", "IR", "KH", "KZ", "LY", "PY", "QA", "RU", "SD", "SY", "VE", "YE", "ZW"} <= codes


def test_full_country_catalog_regions_are_mapped_for_every_country():
    for item in FULL_COUNTRY_CATALOG:
        assert region_for_code(item["code"])
        assert item["region"] == region_for_code(item["code"])
