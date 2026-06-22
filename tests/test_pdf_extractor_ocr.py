from collector.document import pdf_extractor


def test_scanned_like_pdf_uses_ocr_fallback(monkeypatch):
    low_density_pages = [
        {"page_number": index, "text": "Gaceta Oficial Digital"}
        for index in range(1, 8)
    ]
    ocr_pages = [
        {"page_number": 1, "text": "Estrategia Nacional de Ciberseguridad"},
        {"page_number": 2, "text": "infraestructura critica y CSIRT nacional"},
    ]

    monkeypatch.setattr(pdf_extractor, "_try_pypdf_pages", lambda pdf_bytes: low_density_pages)
    monkeypatch.setattr(pdf_extractor, "_try_pdfplumber_pages", lambda pdf_bytes: low_density_pages)
    monkeypatch.setattr(pdf_extractor, "_try_ocr_pages", lambda pdf_bytes: ocr_pages)

    pages = pdf_extractor.extract_page_texts_from_bytes(b"%PDF-1.6 scanned")

    assert pages == ocr_pages
