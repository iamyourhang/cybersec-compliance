from collector.document.chunker import chunk_document_text


def test_chunk_document_text_keeps_clause_reference_and_page_range():
    text = (
        "Chapter I General Provisions\n"
        "Article 1 Scope\n"
        + ("This Regulation applies to connected firewalls and routers. " * 35)
        + "\n\n"
        "Article 2 Essential requirements\n"
        + ("Manufacturers shall provide secure-by-default configurations. " * 35)
    )

    chunks = chunk_document_text(
        page_texts=[
            {"page_number": 1, "text": text},
        ],
        target_size=900,
        overlap=150,
    )

    assert len(chunks) >= 2
    assert chunks[0]["page_from"] == 1
    assert chunks[0]["page_to"] == 1
    assert chunks[0]["clause_ref"] == "Article 1"
    assert "Chapter I" in chunks[0]["section_path"]


def test_chunk_document_text_splits_long_clause_with_overlap():
    long_clause = "第十条 默认安全配置 " + ("设备出厂时必须启用最小权限和日志审计。 " * 220)
    chunks = chunk_document_text(
        page_texts=[
            {"page_number": 4, "text": "第二章 技术要求\n" + long_clause},
        ],
        target_size=1000,
        overlap=160,
    )

    assert len(chunks) >= 2
    assert all(chunk["clause_ref"] == "第十条" for chunk in chunks)
    assert chunks[0]["page_from"] == 4
    assert chunks[1]["content"][:40] in chunks[0]["content"]
