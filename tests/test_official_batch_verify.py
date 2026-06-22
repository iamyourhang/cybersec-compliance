from collector.audit.official_batch_verify import build_official_verification


def test_build_official_verification_accepts_etsi_pdf_with_matching_code():
    result = build_official_verification(
        {
            "name": "ETSI EN 303 645 V2.1.1: Cyber Security for Consumer Internet of Things (IoT); Baseline Requirements",
            "entry_type": "standard",
            "official_url": "https://www.etsi.org/deliver/etsi_en/303600_303699/303645/02.01.01_60/en_303645v020101p.pdf",
        }
    )

    assert result is not None
    assert result["verified"] is True
    assert result["host"] == "www.etsi.org"
    assert "ETSI EN 303 645" in result["evidence"]


def test_build_official_verification_accepts_iec_page_with_matching_code():
    result = build_official_verification(
        {
            "name": "IEC 62443-4-2:2019 Security for industrial automation and control systems - Part 4-2: Technical security requirements for IACS components",
            "entry_type": "standard",
            "official_url": "https://www.iec.ch/standard/62443-4-2/ed-2/en",
        }
    )

    assert result is not None
    assert result["verified"] is True
    assert result["host"] == "www.iec.ch"
    assert "IEC 62443-4-2" in result["evidence"]


def test_build_official_verification_rejects_mismatched_code():
    result = build_official_verification(
        {
            "name": "IEC 62443-4-2 Security for industrial automation and control systems",
            "entry_type": "standard",
            "official_url": "https://www.iec.ch/standard/62586.html",
        }
    )

    assert result is None


def test_build_official_verification_rejects_enisa_keyword_only_productized_scheme():
    result = build_official_verification(
        {
            "name": "EU Cybersecurity Certification Scheme (EUCS) for General Network Equipment",
            "entry_type": "certification",
            "official_url": "https://www.enisa.europa.eu/topics/certification/eu-cybersecurity-certification-schemes/eucs-for-general-network-equipment",
        }
    )

    assert result is None


def test_build_official_verification_accepts_eur_lex_without_www():
    result = build_official_verification(
        {
            "name": "Directive (EU) 2022/2555 of the European Parliament and of the Council on measures for a high common level of cybersecurity across the Union",
            "entry_type": "regulation",
            "official_url": "https://eur-lex.europa.eu/eli/dir/2022/2555/oj",
        }
    )

    assert result is not None
    assert result["verified"] is True
    assert result["host"] == "eur-lex.europa.eu"
