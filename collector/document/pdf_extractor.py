"""
collector/document/pdf_extractor.py
PDF 文本提取 - 只负责从PDF字节数据中提取纯文本
不依赖任何业务逻辑和AI
"""
from __future__ import annotations
import io
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

from collector.document.text_cleaner import clean_extracted_text, clean_page_texts

logger = logging.getLogger(__name__)
OCR_MIN_CHARS_PER_PAGE = 180


def extract_text_from_bytes(pdf_bytes: bytes) -> Tuple[str, int]:
    """
    从PDF字节数据提取文本。
    返回 (文本内容, 页数)
    优先用 pypdf（更轻更稳），失败或文本过少时降级用 pdfplumber。
    """
    text, pages = _try_pypdf(pdf_bytes)
    if text and len(text.strip()) > 100:
        return clean_extracted_text(text), pages

    logger.warning("pypdf提取文本过少，尝试pdfplumber")
    text, pages = _try_pdfplumber(pdf_bytes)
    if text and len(text.strip()) > 100:
        return clean_extracted_text(text), pages

    ocr_pages = _try_ocr_pages(pdf_bytes)
    if ocr_pages:
        ocr_text = "\n\n".join(str(page.get("text") or "") for page in ocr_pages)
        return clean_extracted_text(ocr_text), len(ocr_pages)

    return clean_extracted_text(text), pages


def extract_page_texts_from_bytes(pdf_bytes: bytes) -> List[Dict[str, object]]:
    page_texts = _try_pypdf_pages(pdf_bytes)
    if page_texts and not _needs_ocr_fallback(page_texts):
        return clean_page_texts(page_texts)

    logger.warning("pypdf分页提取文本过少，尝试pdfplumber")
    page_texts = _try_pdfplumber_pages(pdf_bytes)
    if page_texts and not _needs_ocr_fallback(page_texts):
        return clean_page_texts(page_texts)

    ocr_pages = _try_ocr_pages(pdf_bytes)
    if ocr_pages:
        return clean_page_texts(ocr_pages)
    return clean_page_texts(page_texts)


def _needs_ocr_fallback(page_texts: List[Dict[str, object]]) -> bool:
    total_chars = sum(len(str(item.get("text") or "").strip()) for item in page_texts)
    page_count = max(len(page_texts), 1)
    if total_chars < 200:
        return True
    return page_count >= 5 and (total_chars / page_count) < OCR_MIN_CHARS_PER_PAGE


def _try_ocr_pages(pdf_bytes: bytes) -> List[Dict[str, object]]:
    if os.getenv("PDF_OCR_ENABLED", "1").lower() in {"0", "false", "no"}:
        return []
    if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
        logger.warning("OCR 依赖缺失，跳过扫描 PDF 兜底")
        return []

    langs = os.getenv("PDF_OCR_LANGS", "eng+fra+spa")
    try:
        with tempfile.TemporaryDirectory(prefix="pdf_ocr_") as tmpdir:
            tmp_path = Path(tmpdir)
            pdf_path = tmp_path / "source.pdf"
            image_prefix = tmp_path / "page"
            pdf_path.write_bytes(pdf_bytes)
            ocr_dpi = os.getenv("PDF_OCR_DPI", "220")
            subprocess.run(
                ["pdftoppm", "-r", ocr_dpi, "-png", str(pdf_path), str(image_prefix)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=int(os.getenv("PDF_OCR_RENDER_TIMEOUT", "180")),
            )
            page_images = sorted(tmp_path.glob("page-*.png"))
            result: List[Dict[str, object]] = []
            for index, image_path in enumerate(page_images, start=1):
                completed = subprocess.run(
                    ["tesseract", str(image_path), "stdout", "-l", langs, "--psm", "1"],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=int(os.getenv("PDF_OCR_PAGE_TIMEOUT", "45")),
                )
                if completed.returncode != 0:
                    logger.warning("OCR 第 %d 页失败: %s", index, completed.stderr[-500:])
                    text = ""
                else:
                    text = completed.stdout or ""
                result.append({"page_number": index, "text": text})
            logger.info("OCR 提取: %d页, %d字符", len(result), sum(len(item["text"]) for item in result))
            return result
    except Exception as e:
        logger.warning("OCR 提取失败: %s", e)
        return []


def _try_pdfplumber(pdf_bytes: bytes) -> Tuple[str, int]:
    try:
        import pdfplumber
        pages_text = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total_pages = len(pdf.pages)
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
        text = "\n\n".join(pages_text)
        logger.info("pdfplumber 提取: %d页, %d字符", total_pages, len(text))
        return text, total_pages
    except ImportError:
        logger.warning("pdfplumber 未安装，跳过")
        return "", 0
    except Exception as e:
        logger.warning("pdfplumber 失败: %s", e)
        return "", 0


def _try_pdfplumber_pages(pdf_bytes: bytes) -> List[Dict[str, object]]:
    try:
        import pdfplumber

        result = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                result.append({
                    "page_number": index,
                    "text": page.extract_text() or "",
                })
        return result
    except Exception as e:
        logger.warning("pdfplumber 分页提取失败: %s", e)
        return []


def _try_pypdf(pdf_bytes: bytes) -> Tuple[str, int]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages_text = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages_text.append(t)
        text = "\n\n".join(pages_text)
        logger.info("pypdf 提取: %d页, %d字符", len(reader.pages), len(text))
        return text, len(reader.pages)
    except ImportError:
        logger.warning("pypdf 未安装，跳过")
        return "", 0
    except Exception as e:
        logger.warning("pypdf 失败: %s", e)
        return "", 0


def _try_pypdf_pages(pdf_bytes: bytes) -> List[Dict[str, object]]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        result = []
        for index, page in enumerate(reader.pages, start=1):
            result.append({
                "page_number": index,
                "text": page.extract_text() or "",
            })
        return result
    except Exception as e:
        logger.warning("pypdf 分页提取失败: %s", e)
        return []
