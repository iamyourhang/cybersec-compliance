from scripts.seed_global_official_sources import (
    DISABLED_NON_CYBER_SOURCE_NAMES,
    GLOBAL_OFFICIAL_SOURCES,
    build_all_official_sources,
    build_curated_doc_official_sources,
)
from scripts.import_curated_official_docs import CURATED_DOCS
from scripts.promote_official_sources_to_link_only_records import PROMOTABLE_OFFICIAL_SOURCES


def test_global_official_sources_do_not_seed_plain_radio_or_type_approval_sources():
    names = {source["name"] for source in GLOBAL_OFFICIAL_SOURCES}

    assert "NTC Type Approved Equipment" not in names
    assert "ICASA Type Approval" not in names
    assert "NTC Type Approved Equipment" in DISABLED_NON_CYBER_SOURCE_NAMES
    assert "ICASA Type Approval" in DISABLED_NON_CYBER_SOURCE_NAMES


def test_global_official_sources_include_more_cybersecurity_certification_and_law_sources():
    names = {source["name"] for source in GLOBAL_OFFICIAL_SOURCES}

    assert "KISA IoT Security Certification" in names
    assert "TAICS IoT Cybersecurity Certification" in names
    assert "Hong Kong Critical Infrastructure Computer Systems Bill" in names
    assert "Ireland NIS2 and Cyber Fundamentals" in names
    assert "Thailand MDES Cybersecurity Act" in names
    assert "Indonesia Common Criteria and Crypto Module Regulations" in names
    assert "Israel National Cyber Directorate Methodology" in names
    assert "ENISA EUCC Certification Scheme" in names


def test_global_official_sources_include_link_only_gap_research_sources():
    sources = {source["name"]: source for source in GLOBAL_OFFICIAL_SOURCES}

    expected_names = {
        "Guatemala CONCIBER National Cybersecurity Strategy",
        "Paraguay MITIC National Cybersecurity Strategy 2025-2028",
        "Russia Official Publication 187-FZ Critical Information Infrastructure",
        "Zimbabwe ICT Ministry Cyber and Data Protection Act Resources",
        "Iraq National Cyber Security Center",
        "Cambodia CamCERT National CERT",
        "Kazakhstan KNB Laws and Cybersecurity Sources",
        "Iran Official Gazette Cybercrime Law Research Source",
        "Libya Central Bank Information Security Policy",
        "Sudan Ministry of Justice Laws Portal",
        "Syria Ministry of Justice Legal Source",
        "Venezuela TSJ Special Law Against Computer Crimes",
        "Yemen MTIT Cybersecurity and ICT Laws Sources",
    }

    assert expected_names <= set(sources)
    assert all(sources[name]["parser_config"]["official_evidence_url"] for name in expected_names)


def test_global_official_sources_include_new_country_catalog_gap_sources():
    names = {source["name"] for source in GLOBAL_OFFICIAL_SOURCES}

    assert "Albania National Cyber Security Authority" in names
    assert "Cyprus Digital Security Authority and NCCA" in names
    assert "Italy National Cybersecurity Agency" in names
    assert "Malta National Cybersecurity Coordination Centre" in names
    assert "Bhutan GovTech BtCIRT" in names
    assert "Vanuatu Government Cybercrime and CERT Sources" in names
    assert "Timor-Leste ICT and Cybercrime Official Sources" in names
    assert "Armenia Official Cybersecurity and Legal Sources" in names


def test_global_official_sources_include_second_gap_batch_sources():
    sources = {source["name"]: source for source in GLOBAL_OFFICIAL_SOURCES}

    expected_names = {
        "Bahamas Computer Misuse Act Official Laws Source",
        "Barbados Computer Misuse Act Official Laws Source",
        "Guyana Cybercrime Act Parliament Source",
        "Saint Lucia Computer Misuse Act Attorney General Source",
        "Burkina Faso ANSSI Cybersecurity Agency",
        "Benin bjCSIRT Official Source",
        "Botswana Cybercrime and Computer Related Crimes Act",
        "Cabo Verde National Cybersecurity Strategy Government Source",
        "Lesotho Computer Crime and Cyber Security Bill Parliament Source",
        "Mauritius ICTA Cybersecurity and Cybercrime Act Source",
        "Malawi Electronic Transactions and Cyber Security Act",
        "Namibia Cybercrime Bill MICT Source",
        "Rwanda National Cyber Security Authority Documentation",
        "Sierra Leone Cybersecurity and Crime Act MIC Source",
        "Togo National Cybersecurity Agency",
    }

    assert expected_names <= set(sources)
    assert all(sources[name]["parser_config"]["official_evidence_url"] for name in expected_names)


def test_global_official_sources_include_final_gap_batch_sources():
    sources = {source["name"]: source for source in GLOBAL_OFFICIAL_SOURCES}

    expected_names = {
        "Palestine MTDE IT Laws Source",
        "Turkmenistan Cyber Security Law and Certification Source",
        "Solomon Islands MCA SICERT Source",
        "Tuvalu Department of ICT Cybersecurity Source",
        "Belarus National CERT Source",
        "Belize National Assembly Cybercrime Act",
        "Saint Kitts and Nevis Law Commission Electronic Crimes Act",
        "Burundi ARCT Cybercrime Law",
        "Republic of Congo Official Journal Cybersecurity Laws",
        "Djibouti National Cybersecurity Authority",
        "Guinea ANSSI Cybersecurity Legal Framework",
        "Seychelles National Cybersecurity and Cybercrimes Sources",
        "Somalia NCA Cybersecurity Law Source",
        "Eswatini Computer Crime and Cybercrime Act",
    }

    assert expected_names <= set(sources)
    assert all(sources[name]["parser_config"]["official_evidence_url"] for name in expected_names)


def test_curated_docs_are_exposed_as_official_source_seeds_without_verifying():
    curated_sources = build_curated_doc_official_sources()
    names = {source["name"] for source in curated_sources}

    assert "Curated Official Evidence - CERT-In Cyber Security Directions 2022" in names
    assert "Curated Official Evidence - South Africa Cybercrimes Act 19 of 2020" in names
    assert all(source["name"].startswith("Curated Official Evidence - ") for source in curated_sources)
    assert all(source["source_type"] in {"html_list", "pdf_index"} for source in curated_sources)
    assert all(source["allowed_domains"] for source in curated_sources)


def test_all_official_source_seeds_remain_network_cybersecurity_scoped():
    names = {source["name"] for source in build_all_official_sources()}

    assert "NTC Type Approved Equipment" not in names
    assert "ICASA Type Approval" not in names
    assert any(source["country_code"] == "NL" for source in build_all_official_sources())


def test_curated_docs_include_next_batch_cybersecurity_only_records():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Singapore Cybersecurity Labelling Scheme for IoT" in names
    assert "ANATEL Ato 77 Cybersecurity Requirements for Telecommunications Equipment" in names
    assert "Malaysian Common Criteria Evaluation and Certification Scheme" in names
    assert "BSI IT Security Label" in names
    assert "ANSSI CSPN First Level Security Certification" in names
    assert "CERT-In Cyber Security Directions 2022" in names


def test_curated_docs_include_additional_official_cybersecurity_markets():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Ireland NIS2 Guidance" in names
    assert "Ireland Cyber Fundamentals Framework" in names
    assert "UAE National IoT Security Policy" in names
    assert "Saudi Arabia IoT Regulations" in names
    assert "Mexico IFT IoT Cybersecurity Best Practices Code" in names
    assert "New Zealand ISO/IEC 27402 IoT Security Baseline" in names
    assert "New Zealand Cyber Security Strategy 2026-2030" in names
    assert "Philippines DICT Trusted Cybersecurity Assessment Providers" in names
    assert "Philippines National Cybersecurity Plan 2023-2028" in names


def test_curated_docs_include_europe_asia_and_africa_cyber_law_batch():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Spain National Security Framework (ENS) Royal Decree 311/2022" in names
    assert "Estonia Cybersecurity Act" in names
    assert "Lithuania Law on Cyber Security" in names
    assert "South Africa Cybercrimes Act 19 of 2020" in names
    assert "Vietnam Law on Network Information Security No. 86/2015/QH13" in names
    assert "Croatia Cybersecurity Act" in names
    assert "Czech Act on Cyber Security No. 264/2025 Coll." in names


def test_curated_docs_include_core_china_cybersecurity_laws_and_certification_catalogues():
    names = {item["name"] for item in CURATED_DOCS}

    assert "中华人民共和国网络安全法（2025年修正）" in names
    assert "中华人民共和国数据安全法" in names
    assert "关键信息基础设施安全保护条例" in names
    assert "Cybersecurity Review Measures" in names
    assert "Regulations on the Security Vulnerability Management of Network Products" in names
    assert "Catalogue of Critical Network Equipment and Specialized Cybersecurity Products" in names
    assert "GB 42250-2022 Information security technology - Security technical requirements for specialized cybersecurity products" in names
    assert "GB/T 22239-2019 Information security technology - Baseline for classified protection of cybersecurity" in names
    assert "Commercial Cryptography Product Certification" in names
    assert "Network Critical Equipment and Specialized Cybersecurity Products Certification Implementation Rules" in names
    assert "Network Critical Equipment and Specialized Cybersecurity Products Certification and Testing Results Registry" in names


def test_curated_docs_include_next_global_official_cybersecurity_batch():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Chile Framework Law on Cybersecurity and Critical Information Infrastructure" in names
    assert "Ghana Cybersecurity Act 2020 (Act 1038)" in names
    assert "Kenya Computer Misuse and Cybercrimes Act No. 5 of 2018" in names
    assert "Kenya Critical Information Infrastructure and Cybercrime Management Regulations 2024" in names
    assert "Qatar National Information Assurance Certification and Standard v2.1" in names
    assert "Poland Act on National Cybersecurity System" in names
    assert "Poland Act on National Cybersecurity Certification System 2025" in names
    assert "Turkey Cybersecurity Law No. 7545" in names
    assert "Switzerland Mandatory Cyberattack Reporting Legal Bases" in names
    assert "Nigeria Cybercrimes Amendment Act 2024" in names


def test_curated_docs_include_africa_gap_verified_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Senegal Law No. 2008-11 on Cybercrime" in names
    assert "Tanzania Cybercrimes Act 2015" in names
    assert "Uganda Computer Misuse Act 2011" in names
    assert "Zambia Cyber Security and Cyber Crimes Act No. 2 of 2021" in names


def test_curated_docs_include_next_european_official_cybersecurity_batch():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Austria Network and Information System Security Act" in names
    assert "Denmark Act on Measures to Ensure a High Cybersecurity Level" in names
    assert "Finland Cybersecurity Act 124/2025" in names
    assert "Latvia National Cybersecurity Law" in names
    assert "Slovakia Cybersecurity Act No. 69/2018 Coll." in names
    assert "Slovenia Information Security Act (ZInfV-1)" in names
    assert "Romania Emergency Ordinance No. 155/2024 on Cybersecurity" in names
    assert "Norway NSM ICT Security Principles v2.1" in names


def test_curated_docs_include_additional_verified_european_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Portugal Law No. 46/2018 Cyberspace Security Legal Regime" in names
    assert "Greece Law 5160/2024 NIS2 Cybersecurity Transposition" in names


def test_curated_docs_include_benelux_verified_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Belgium NIS2 Law of 26 April 2024" in names
    assert "Netherlands Network and Information Systems Security Act (Wbni)" in names
    assert "Luxembourg NIS Law of 28 May 2019" in names


def test_curated_docs_include_nordic_verified_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Sweden Information Security for Essential and Digital Services Act (2018:1174)" in names


def test_curated_docs_include_eastern_europe_verified_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Bulgaria Cybersecurity Act" in names
    assert "Ukraine Law on the Basic Principles of Cybersecurity" in names
    assert "Hungary Act LXIX of 2024 on Cybersecurity" in names


def test_curated_docs_include_latin_america_verified_cybersecurity_requirements():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Argentina Minimum Information Security Requirements for Public Sector Bodies" in names
    assert "Colombia CONPES 3995 National Digital Trust and Security Policy" in names
    assert "Costa Rica National Cybersecurity Strategy 2023-2027" in names
    assert "Ecuador National Cybersecurity Strategy 2022-2025" in names
    assert "Panama National Cybersecurity Strategy 2021-2024" in names
    assert "Uruguay AGESIC Cybersecurity Framework v5.0" in names
    assert "Peru Digital Trust Framework Emergency Decree No. 007-2020" in names
    assert "Peru Digital Trust Framework Regulation Supreme Decree No. 126-2025-PCM" in names


def test_curated_docs_attach_user_supplied_scanned_official_artifacts():
    items = {item["name"]: item for item in CURATED_DOCS}

    assert items["Panama National Cybersecurity Strategy 2021-2024"]["local_file"].endswith(
        "pa_gaceta_29434_a_estrategia_ciberseguridad_2021.pdf"
    )
    assert items["Senegal Law No. 2008-11 on Cybercrime"]["local_file"].endswith(
        "sn_loi_2008_11_cybercriminalite.pdf"
    )
    assert items["Nigeria Cybercrimes Amendment Act 2024"]["local_file"].endswith(
        "ng_cybercrimes_amendment_act_2024.pdf"
    )


def test_curated_docs_include_north_africa_verified_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Algeria Law No. 09-04 on ICT-related Offences" in names
    assert "Morocco Law No. 05-20 on Cybersecurity" in names
    assert "Egypt NTRA Internet of Things Regulatory Framework" in names
    assert "Tunisia National Cybersecurity Strategy 2020-2025" in names


def test_curated_docs_include_common_criteria_product_certification_batch():
    names = {item["name"] for item in CURATED_DOCS}

    assert "US NIAP Common Criteria Evaluation and Validation Scheme" in names
    assert "Canada Common Criteria Program" in names
    assert "India Common Criteria Certification Scheme (IC3S)" in names
    assert "Japan IT Security Evaluation and Certification Scheme (JISEC)" in names
    assert "Singapore Common Criteria Scheme (SCCS)" in names
    assert "Spain CCN Common Criteria Certification Body" in names
    assert "Norway SERTIT Common Criteria Certification Scheme" in names
    assert "Sweden CSEC Common Criteria Product Certification" in names
    assert "Turkey TSE Common Criteria Certification Services" in names


def test_curated_docs_include_middle_east_verified_cybersecurity_requirements():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Bahrain CBB Insurance Rulebook Cyber Security Risk Management" in names
    assert "Kuwait National Cyber Security Strategy 2017-2020" in names
    assert "Oman Open Banking Regulatory Framework Cybersecurity Controls" in names


def test_curated_docs_include_south_asia_verified_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Bangladesh Cyber Security Ordinance 2025" in names
    assert "Nepal National Cyber Security Policy 2023" in names
    assert "Pakistan National Cyber Security Policy 2021" in names
    assert "Sri Lanka Computer Crime Act No. 24 of 2007" in names


def test_curated_docs_include_asia_gap_verified_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Brunei Cybersecurity Order 2023" in names
    assert "Mongolia Law on Cyber Security" in names
    assert "Uzbekistan Law on Cybersecurity ZRU-764" in names


def test_curated_docs_include_caucasus_verified_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Azerbaijan Information and Cybersecurity Strategy 2023-2027" in names
    assert "Georgia Law on Information Security" in names


def test_curated_docs_include_western_balkans_verified_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Serbia Law on Information Security 2025" in names


def test_curated_docs_include_caribbean_verified_cybersecurity_laws():
    names = {item["name"] for item in CURATED_DOCS}

    assert "Dominican Republic National Cybersecurity Strategy 2030 Decree 313-22" in names
    assert "Jamaica Cybercrimes Act" in names
    assert "Trinidad and Tobago Computer Misuse Act" in names


def test_promotable_official_sources_are_specific_not_generic_homepages():
    names = {item["record_name"] for item in PROMOTABLE_OFFICIAL_SOURCES}
    source_names = {item["source_name"] for item in PROMOTABLE_OFFICIAL_SOURCES}

    assert "Barbados Computer Misuse Act" in names
    assert "Republic of Congo Law No. 27-2020 on Cybersecurity" in names
    assert "Russia Federal Law No. 187-FZ on Critical Information Infrastructure Security" in names
    assert "Andorra National Cybersecurity Agency" not in source_names
    assert "Italy National Cybersecurity Agency" not in source_names
