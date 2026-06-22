"""
Sanitization helpers for text extracted from official PDFs/HTML.

PostgreSQL text/jsonb values cannot contain NUL bytes. Some official PDFs
produce hidden NUL characters during extraction, so normalize once near the
document boundary before parsing, indexing, or storing.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

_UNUSABLE_TEXT_MARKERS = (
    "please enable javascript",
    "enable javascript to view the page content",
    "your browser is not compatible",
    "navegador no sea compatible",
    "este proceso demora demasiado",
    "cf-mitigated",
    "checking your browser",
)


def clean_extracted_text(value: Any) -> str:
    """Return a DB-safe text string while preserving normal whitespace/content."""
    if value is None:
        return ""
    return str(value).replace("\x00", "")


def clean_page_texts(page_texts: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned_pages: List[Dict[str, Any]] = []
    for page in page_texts:
        cleaned = dict(page)
        cleaned["text"] = clean_extracted_text(cleaned.get("text"))
        cleaned_pages.append(cleaned)
    return cleaned_pages


def is_unusable_extracted_text(value: str) -> bool:
    """Detect browser challenge / compatibility pages that are not source text."""
    lowered = clean_extracted_text(value).lower()
    return any(marker in lowered for marker in _UNUSABLE_TEXT_MARKERS)
