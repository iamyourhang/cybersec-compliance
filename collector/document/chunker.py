"""
collector/document/chunker.py
法律法规文本切分：标题/条款优先，长度兜底。
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Any, Dict, List, Optional

HEADING_RE = re.compile(
    r"(?im)^(?P<raw>(chapter\s+[ivxlcdm]+|section\s+\d+|annex\s+[a-z0-9]+|"
    r"article\s+\d+[a-z\-]*|第[一二三四五六七八九十百千0-9]+[章节条]|附件[一二三四五六七八九十0-9A-Za-z]+).*)$"
)

CLAUSE_RE = re.compile(r"(?i)(article\s+\d+[a-z\-]*|第[一二三四五六七八九十百千0-9]+条)")
SECTION_REF_RE = re.compile(
    r"(?i)^(chapter\s+[ivxlcdm]+|section\s+\d+|annex\s+[a-z0-9]+|article\s+\d+[a-z\-]*|"
    r"第[一二三四五六七八九十百千0-9]+[章节条]|附件[一二三四五六七八九十0-9A-Za-z]+)"
)
TOC_TITLE_RE = re.compile(r"(?i)\b(table of contents|contents)\b|目录")
DOT_LEADER_RE = re.compile(r"\.{4,}|·{4,}|…{2,}")
TRAILING_PAGE_RE = re.compile(r"(?:\.{2,}|\s{2,}|\t)\s*\d{1,4}$|\b\d{1,4}\s*$")
NOISE_TITLE_RE = re.compile(r"^[\W_]+$|^[0-9.\-:()]+$")


def chunk_document_text(
    page_texts: List[Dict[str, object]],
    target_size: int = 1200,
    overlap: int = 150,
) -> List[Dict[str, object]]:
    chunks: List[Dict[str, object]] = []
    current_section: List[str] = []

    for page in page_texts:
        page_number = int(page["page_number"])
        page_chunks, current_section = _chunk_single_page(
            text=str(page.get("text") or ""),
            page_number=page_number,
            current_section=current_section,
            target_size=target_size,
            overlap=overlap,
        )
        chunks.extend(page_chunks)

    return chunks


def extract_document_sections(page_texts: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return extract_document_sections_with_diagnostics(page_texts)["sections"]


def extract_document_sections_with_diagnostics(page_texts: List[Dict[str, object]]) -> Dict[str, Any]:
    sections: List[Dict[str, object]] = []
    current_section: Optional[Dict[str, object]] = None
    current_path: List[str] = []
    diagnostics: Dict[str, Any] = {
        "parsed_count": 0,
        "filtered_count": 0,
        "filtered_reason_summary": {},
    }
    filtered_reasons: Counter[str] = Counter()
    filtered_count = 0

    for page in page_texts:
        page_number = int(page["page_number"])
        text = str(page.get("text") or "")
        if not text.strip():
            continue
        page_classification = _classify_page(text)
        if page_classification["page_type"] == "table_of_contents":
            filtered_reasons.update(page_classification["reasons"])
            filtered_count += 1
            continue
        for raw_line in re.sub(r"\r\n?", "\n", text).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            heading = _parse_heading_line(line)
            if heading and heading["accepted"]:
                if current_section is not None:
                    sections.append(_finalize_section(current_section))
                current_path = _update_section_path(current_path, heading["raw"])
                current_section = {
                    "section_type": heading["section_type"],
                    "section_ref": heading["section_ref"],
                    "title": heading["title"],
                    "section_path": " > ".join(current_path),
                    "page_from": page_number,
                    "page_to": page_number,
                    "content": "",
                    "parse_confidence": heading["parse_confidence"],
                    "parse_reason": heading["parse_reason"],
                }
                continue
            if heading and not heading["accepted"]:
                filtered_reasons.update([str(heading["parse_reason"] or "low_confidence_heading")])
                filtered_count += 1
                continue

            if current_section is None:
                current_section = {
                    "section_type": "preamble",
                    "section_ref": "Preamble",
                    "title": None,
                    "section_path": "",
                    "page_from": page_number,
                    "page_to": page_number,
                    "content": line,
                }
            else:
                current_section["content"] = (
                    f"{current_section['content']}\n{line}".strip()
                    if current_section["content"]
                    else line
                )
                current_section["page_to"] = page_number

    if current_section is not None:
        sections.append(_finalize_section(current_section))

    for index, section in enumerate(sections):
        section["section_index"] = index
    diagnostics["parsed_count"] = len(sections)
    diagnostics["filtered_count"] = filtered_count
    diagnostics["filtered_reason_summary"] = dict(filtered_reasons)
    return {"sections": sections, "diagnostics": diagnostics}


def _chunk_single_page(
    text: str,
    page_number: int,
    current_section: List[str],
    target_size: int,
    overlap: int,
) -> tuple[List[Dict[str, object]], List[str]]:
    if not text.strip():
        return [], current_section

    blocks = _split_blocks(text)
    chunks: List[Dict[str, object]] = []

    for block in blocks:
        heading_match = HEADING_RE.match(block)
        if heading_match:
            current_section = _update_section_path(current_section, heading_match.group("raw"))

        clause_ref = _extract_clause_ref(block)
        if len(block) <= target_size:
            chunks.append(
                _build_chunk(
                    content=block,
                    page_number=page_number,
                    section_path=current_section,
                    clause_ref=clause_ref,
                )
            )
            continue

        chunks.extend(
            _split_long_block(
                block=block,
                page_number=page_number,
                section_path=current_section,
                clause_ref=clause_ref,
                target_size=target_size,
                overlap=overlap,
            )
        )

    return chunks, current_section


def _split_blocks(text: str) -> List[str]:
    normalized = re.sub(r"\r\n?", "\n", text)
    starts = [m.start() for m in HEADING_RE.finditer(normalized)]
    if not starts:
        return [segment.strip() for segment in normalized.split("\n\n") if segment.strip()]

    starts.append(len(normalized))
    blocks: List[str] = []
    for idx in range(len(starts) - 1):
        block = normalized[starts[idx]:starts[idx + 1]].strip()
        if block:
            blocks.append(block)
    return _merge_heading_only_blocks(blocks)


def _merge_heading_only_blocks(blocks: List[str]) -> List[str]:
    if not blocks:
        return []
    merged: List[str] = []
    for block in blocks:
        if _is_heading_only(block) and merged:
            merged[-1] = f"{merged[-1]}\n{block}".strip()
            continue
        if _is_heading_only(block):
            merged.append(block)
            continue
        if merged and _is_heading_only(merged[-1]):
            merged[-1] = f"{merged[-1]}\n{block}".strip()
        else:
            merged.append(block)
    return merged


def _is_heading_only(block: str) -> bool:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) != 1:
        return False
    return bool(HEADING_RE.match(lines[0])) and not _extract_clause_ref(lines[0])


def _update_section_path(current_section: List[str], heading: str) -> List[str]:
    cleaned = heading.strip()
    lower = cleaned.lower()
    if lower.startswith(("chapter", "第")) and ("章" in cleaned or lower.startswith("chapter")):
        return [cleaned]
    if lower.startswith(("section", "annex", "附件")):
        return current_section[:1] + [cleaned]
    if lower.startswith("article") or "条" in cleaned:
        return current_section[:2] + [cleaned]
    return current_section + [cleaned]


def _extract_clause_ref(text: str) -> Optional[str]:
    match = CLAUSE_RE.search(text)
    return match.group(1) if match else None


def _parse_heading_line(line: str) -> Optional[Dict[str, object]]:
    heading_match = HEADING_RE.match(line)
    if not heading_match:
        return None
    raw = heading_match.group("raw").strip()
    ref_match = SECTION_REF_RE.match(raw)
    if not ref_match:
        return None
    if _is_toc_heading_line(raw):
        return {
            "accepted": False,
            "raw": raw,
            "parse_confidence": 0.05,
            "parse_reason": "toc_heading_line",
        }
    section_ref = ref_match.group(1).strip()
    title = raw[len(section_ref):].strip(" :-\t") or None
    confidence = 0.6
    reason = "accepted"
    if title and 3 <= len(title) <= 220 and not _looks_like_noise_title(title):
        confidence += 0.25
    elif title:
        confidence -= 0.2
        reason = "low_confidence_heading"
    if len(raw) > 180:
        confidence -= 0.15
        reason = "low_confidence_heading"
    if title and DOT_LEADER_RE.search(title):
        confidence = 0.05
        reason = "toc_heading_line"
    accepted = confidence >= 0.75
    return {
        "accepted": accepted,
        "raw": raw,
        "section_type": _infer_section_type(section_ref),
        "section_ref": section_ref,
        "title": title,
        "parse_confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "parse_reason": "accepted" if accepted else reason,
    }


def _infer_section_type(section_ref: str) -> str:
    lower = section_ref.lower()
    if lower.startswith("chapter") or "章" in section_ref:
        return "chapter"
    if lower.startswith("section") or "节" in section_ref:
        return "section"
    if lower.startswith("article") or "条" in section_ref:
        return "article"
    if lower.startswith("annex") or section_ref.startswith("附件"):
        return "annex"
    return "section"


def _finalize_section(section: Dict[str, object]) -> Dict[str, object]:
    finalized = dict(section)
    finalized["content"] = str(finalized.get("content") or "").strip()
    return finalized


def _classify_page(text: str) -> Dict[str, object]:
    lines = [line.strip() for line in re.sub(r"\r\n?", "\n", text).splitlines() if line.strip()]
    if not lines:
        return {"page_type": "empty", "reasons": []}
    heading_candidates = [line for line in lines if SECTION_REF_RE.match(line)]
    toc_styled_lines = [line for line in lines if _is_toc_heading_line(line)]
    short_lines = [line for line in lines if len(line) <= 90]
    first_lines = " ".join(lines[:3])
    reasons: List[str] = []

    if TOC_TITLE_RE.search(first_lines):
        reasons.append("table_of_contents_page")
    if len(toc_styled_lines) >= 3:
        reasons.append("table_of_contents_page")
    if (
        len(heading_candidates) >= 3
        and len(short_lines) >= max(3, int(len(lines) * 0.7))
        and sum(1 for line in lines if TRAILING_PAGE_RE.search(line)) >= 2
    ):
        reasons.append("table_of_contents_page")

    page_type = "table_of_contents" if reasons else "body"
    return {"page_type": page_type, "reasons": reasons}


def _is_toc_heading_line(line: str) -> bool:
    normalized = " ".join(line.split())
    if not SECTION_REF_RE.match(normalized):
        return False
    return bool(DOT_LEADER_RE.search(normalized) or TRAILING_PAGE_RE.search(normalized))


def _looks_like_noise_title(title: str) -> bool:
    cleaned = title.strip()
    if not cleaned:
        return True
    if NOISE_TITLE_RE.match(cleaned):
        return True
    if len(cleaned) < 2:
        return True
    return False


def _split_long_block(
    block: str,
    page_number: int,
    section_path: List[str],
    clause_ref: Optional[str],
    target_size: int,
    overlap: int,
) -> List[Dict[str, object]]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", block) if p.strip()]
    if len(paragraphs) == 1:
        paragraphs = _soft_wrap(block, target_size=target_size, overlap=overlap)

    chunks: List[Dict[str, object]] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > target_size:
            chunks.append(
                _build_chunk(
                    content=current,
                    page_number=page_number,
                    section_path=section_path,
                    clause_ref=clause_ref,
                )
            )
            current = _tail_overlap(current, overlap)
        current = f"{current}\n\n{paragraph}".strip() if current else paragraph

    if current:
        chunks.append(
            _build_chunk(
                content=current,
                page_number=page_number,
                section_path=section_path,
                clause_ref=clause_ref,
            )
        )
    return chunks


def _soft_wrap(text: str, target_size: int, overlap: int) -> List[str]:
    wrapped: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + target_size, len(text))
        wrapped.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return [item for item in wrapped if item]


def _tail_overlap(text: str, overlap: int) -> str:
    if len(text) <= overlap:
        return text
    return text[-overlap:]


def _build_chunk(
    content: str,
    page_number: int,
    section_path: List[str],
    clause_ref: Optional[str],
) -> Dict[str, object]:
    return {
        "page_from": page_number,
        "page_to": page_number,
        "section_path": " > ".join(section_path),
        "clause_ref": clause_ref,
        "content": content.strip(),
    }
