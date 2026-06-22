from __future__ import annotations

from collector.translation.service import (
    TranslationField,
    TranslationJob,
    attach_translation_fields,
    build_translation_jobs,
    extract_text_values,
    is_translatable_value,
    merge_hash_reuse,
    stable_text_hash,
)


def test_is_translatable_value_skips_urls_dates_codes_and_short_statuses():
    assert is_translatable_value("Cyber Resilience Act")
    assert is_translatable_value("Official PDF verified by EU source.")
    assert not is_translatable_value("https://eur-lex.europa.eu/legal-content/EN/TXT/")
    assert not is_translatable_value("2026-05-09")
    assert not is_translatable_value("P1")
    assert not is_translatable_value("active")
    assert not is_translatable_value("home_router")
    assert not is_translatable_value("已经是中文的内容")
    assert is_translatable_value("Curated Official Evidence - 中华人民共和国网络安全法")
    assert not is_translatable_value("")


def test_extract_text_values_flattens_lists_and_json_but_preserves_paths():
    values = extract_text_values(
        "requirements",
        {
            "scope": "Products with digital elements",
            "items": ["secure by default", "2026-05-09", {"title": "vulnerability handling"}],
            "url": "https://example.gov/law.pdf",
        },
    )

    assert values == [
        TranslationField(field_name="requirements.scope", source_text="Products with digital elements"),
        TranslationField(field_name="requirements.items[0]", source_text="secure by default"),
        TranslationField(field_name="requirements.items[2].title", source_text="vulnerability handling"),
    ]


def test_stable_text_hash_is_content_based_and_whitespace_normalized():
    assert stable_text_hash(" Cyber   Resilience Act ") == stable_text_hash("Cyber Resilience Act")
    assert stable_text_hash("Cyber Resilience Act") != stable_text_hash("NIS2 Directive")


def test_attach_translation_fields_preserves_original_and_adds_zh_suffixes():
    row = {
        "id": "record-1",
        "name": "Cyber Resilience Act",
        "summary": "Security requirements for products with digital elements.",
    }
    translations = {
        ("record-1", "name"): "《网络韧性法案》",
        ("record-1", "summary"): "适用于带有数字元素产品的安全要求。",
    }

    enriched = attach_translation_fields(row, translations, entity_id_field="id")

    assert enriched["name"] == "Cyber Resilience Act"
    assert enriched["name_zh"] == "《网络韧性法案》"
    assert enriched["summary_zh"] == "适用于带有数字元素产品的安全要求。"
    assert enriched["translations"] == {
        "name": "《网络韧性法案》",
        "summary": "适用于带有数字元素产品的安全要求。",
    }


def test_build_translation_jobs_keeps_each_field_and_hashes_source_text():
    rows = [
        {
            "id": "record-1",
            "name": "Cyber Resilience Act",
            "summary": "Cyber Resilience Act",
            "official_url": "https://example.gov/cra",
        }
    ]

    jobs = build_translation_jobs(
        entity_type="compliance_index",
        rows=rows,
        translatable_fields=["name", "summary", "official_url"],
    )

    assert jobs == [
        TranslationJob(
            entity_type="compliance_index",
            entity_id="record-1",
            field_name="name",
            source_text="Cyber Resilience Act",
            source_text_hash=stable_text_hash("Cyber Resilience Act"),
        ),
        TranslationJob(
            entity_type="compliance_index",
            entity_id="record-1",
            field_name="summary",
            source_text="Cyber Resilience Act",
            source_text_hash=stable_text_hash("Cyber Resilience Act"),
        ),
    ]


def test_merge_hash_reuse_reuses_existing_translation_for_same_text_hash():
    pending = [
        TranslationJob("compliance_index", "record-1", "name", "Cyber Resilience Act", stable_text_hash("Cyber Resilience Act")),
        TranslationJob("source_records", "source-1", "title", "Cyber Resilience Act", stable_text_hash("Cyber Resilience Act")),
    ]
    existing_by_hash = {stable_text_hash("Cyber Resilience Act"): "《网络韧性法案》"}

    reused, remaining = merge_hash_reuse(pending, existing_by_hash)

    assert reused == {
        ("compliance_index", "record-1", "name", stable_text_hash("Cyber Resilience Act")): "《网络韧性法案》",
        ("source_records", "source-1", "title", stable_text_hash("Cyber Resilience Act")): "《网络韧性法案》",
    }
    assert remaining == []
