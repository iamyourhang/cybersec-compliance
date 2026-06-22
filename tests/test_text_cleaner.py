from collector.document.text_cleaner import (
    clean_extracted_text,
    clean_page_texts,
    is_unusable_extracted_text,
)


def test_clean_extracted_text_strips_postgres_unsafe_nul_characters():
    assert clean_extracted_text("Article 1\x00 must report incidents") == "Article 1 must report incidents"


def test_clean_page_texts_preserves_metadata_and_cleans_text():
    pages = [
        {"page_number": 1, "text": "Clause A\x00 text"},
        {"page_number": 2, "text": None, "source": "pdf"},
    ]

    cleaned = clean_page_texts(pages)

    assert cleaned[0]["page_number"] == 1
    assert cleaned[0]["text"] == "Clause A text"
    assert cleaned[1]["source"] == "pdf"
    assert cleaned[1]["text"] == ""


def test_is_unusable_extracted_text_detects_browser_compatibility_pages():
    text = (
        "Ley Chile - Biblioteca del Congreso Nacional Ley Chile\n"
        "Este proceso demora demasiado, es probable que su conexión esté muy lenta "
        "o que su navegador no sea compatible con nuestra aplicación."
    )

    assert is_unusable_extracted_text(text) is True
    assert is_unusable_extracted_text("Article 1 Organizations must report cybersecurity incidents.") is False
