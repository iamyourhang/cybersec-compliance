"""
collector/document/html_extractor.py
HTML 正文提取：把官方正文页抽成可解析、可索引、可提规格的纯文本。
"""
from __future__ import annotations

import html
import logging
import re
from html.parser import HTMLParser
from typing import Dict, List, Tuple

from collector.document.text_cleaner import clean_extracted_text

logger = logging.getLogger(__name__)

_BLOCK_TAGS = {
    "title",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "div",
    "section",
    "article",
    "main",
    "td",
    "th",
    "blockquote",
}
_SKIP_TAGS = {"script", "style", "noscript"}


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._stack: list[str] = []
        self._buffer: list[str] = []
        self._blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        self._stack.append(tag)
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if self._stack:
            self._stack.pop()
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag in _BLOCK_TAGS:
            self._flush_block()

    def handle_data(self, data: str):
        if self._skip_depth:
            return
        cleaned = _clean_text(data)
        if cleaned:
            self._buffer.append(cleaned)

    def get_text(self) -> str:
        self._flush_block()
        return "\n".join(self._blocks)

    def _flush_block(self):
        if not self._buffer:
            return
        text = _clean_text(" ".join(self._buffer))
        self._buffer = []
        if not text:
            return
        if len(text) < 2:
            return
        if self._blocks and self._blocks[-1] == text:
            return
        self._blocks.append(text)


def _clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = clean_extracted_text(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def extract_text_from_html_bytes(html_bytes: bytes) -> Tuple[str, int]:
    text = _extract_html_text(html_bytes)
    logger.info("html 提取: 1页, %d字符", len(text))
    return text, 1


def extract_page_texts_from_html_bytes(html_bytes: bytes) -> List[Dict[str, object]]:
    text = _extract_html_text(html_bytes)
    return [{"page_number": 1, "text": text}]


def _extract_html_text(html_bytes: bytes) -> str:
    parser = _TextParser()
    parser.feed(html_bytes.decode("utf-8", errors="ignore"))
    return parser.get_text()
