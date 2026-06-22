"""
collector/document/index_service.py
法规文档索引：分页提取 -> 切分 -> embedding -> 入库。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Dict, List, Optional

from collector.document.chunker import chunk_document_text
from collector.document.chunker import extract_document_sections_with_diagnostics
from collector.document.cos_storage import CosStorage
from collector.document.doc_repository import DocRepository
from collector.document.embedder import EmbeddingService
from collector.document.html_extractor import extract_page_texts_from_html_bytes
from collector.document.pdf_extractor import extract_page_texts_from_bytes
from collector.document.text_cleaner import clean_page_texts, is_unusable_extracted_text
from database.repository import RegulationChunkRepository, RegulationSectionRepository

logger = logging.getLogger(__name__)


class DocumentIndexService:
    def __init__(
        self,
        storage: Optional[CosStorage] = None,
        embedder: Optional[EmbeddingService] = None,
    ):
        self._storage = storage or CosStorage()
        self._embedder = embedder or EmbeddingService()

    def index_document(self, doc_id: str) -> Dict:
        doc = DocRepository.get(doc_id)
        if not doc:
            raise ValueError(f"文档不存在: {doc_id}")

        DocRepository.set_indexing(doc_id, 10, "下载并提取分页文本")
        content_bytes = self._storage.download_bytes(doc["cos_key"])
        if (doc.get("file_type") or "").lower() == "html":
            page_texts = extract_page_texts_from_html_bytes(content_bytes)
        else:
            page_texts = extract_page_texts_from_bytes(content_bytes)
        page_texts = clean_page_texts(page_texts)
        joined_text = "\n\n".join(page["text"] for page in page_texts if page["text"])
        if len(joined_text.strip()) < 200 or is_unusable_extracted_text(joined_text):
            raise ValueError("当前版本不支持不可提取文本的源文件，请上传可复制文本 PDF 或稳定正文页")

        content_hash = hashlib.sha256(joined_text.encode("utf-8")).hexdigest()
        section_result = extract_document_sections_with_diagnostics(page_texts=page_texts)
        sections = section_result["sections"]
        diagnostics = section_result["diagnostics"]
        chunks = chunk_document_text(page_texts=page_texts)
        if not chunks:
            raise ValueError("未能从文档中生成可索引片段")

        DocRepository.set_indexing(doc_id, 40, f"开始写入 {len(sections)} 个条款结构和 {len(chunks)} 个切片")
        vectors = self._embedder.embed_texts(chunk["content"] for chunk in chunks)

        RegulationSectionRepository.delete_by_document(doc_id)
        RegulationChunkRepository.delete_by_document(doc_id)
        RegulationSectionRepository.create_sections(
            doc=doc,
            sections=sections,
        )
        RegulationChunkRepository.create_chunks(
            doc=doc,
            chunks=chunks,
            vectors=vectors,
        )
        DocRepository.set_index_diagnostics(doc_id, diagnostics)

        DocRepository.set_indexed(
            doc_id,
            page_count=len(page_texts),
            chunk_count=len(chunks),
            content_hash=content_hash,
        )
        logger.info("✅ 文档索引完成 [%s] chunks=%d", doc_id, len(chunks))
        return {
            "success": True,
            "doc_id": doc_id,
            "page_count": len(page_texts),
            "chunk_count": len(chunks),
            "content_hash": content_hash,
            "index_diagnostics": diagnostics,
        }
