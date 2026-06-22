from collector.document.html_extractor import (
    extract_page_texts_from_html_bytes,
    extract_text_from_html_bytes,
)


def test_extract_text_from_html_bytes_keeps_substantive_blocks():
    html = b"""
    <html>
      <head>
        <title>Cybersecurity Rules 2025</title>
        <style>.hidden { display:none; }</style>
      </head>
      <body>
        <main>
          <h1>Cybersecurity Rules 2025</h1>
          <p>Article 1 This regulation applies to smart devices and network equipment.</p>
          <p>Article 2 Manufacturers must provide secure software updates.</p>
          <script>console.log('ignore')</script>
        </main>
      </body>
    </html>
    """

    text, pages = extract_text_from_html_bytes(html)

    assert pages == 1
    assert "Cybersecurity Rules 2025" in text
    assert "Article 1" in text
    assert "secure software updates" in text
    assert "console.log" not in text


def test_extract_page_texts_from_html_bytes_returns_single_page():
    html = b"<html><body><h1>Title</h1><p>Clause 1 text.</p></body></html>"

    pages = extract_page_texts_from_html_bytes(html)

    assert len(pages) == 1
    assert pages[0]["page_number"] == 1
    assert "Clause 1 text." in pages[0]["text"]
