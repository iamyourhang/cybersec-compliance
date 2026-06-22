"""
collector/document/retrieval_service.py
混合召回：向量 + 关键词。
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, List, Optional

from collector.document.embedder import EmbeddingService
from database.connection import get_cursor
from database.repository import (
    ComplianceIndexRepository,
    ComplianceRepository,
    RegulationChunkRepository,
    RegulationSectionRepository,
    RegulationSpecRequirementRepository,
)


_PRODUCT_QUERY_HINTS = {
    "switch": ("交换机", "switch", "switches"),
    "enterprise_router": ("企业路由", "企业级路由", "路由器", "router", "routers"),
    "home_router": ("家用路由", "home router", "consumer router"),
    "firewall_utm": ("防火墙", "firewall", "utm"),
    "wireless_ap": ("无线ap", "无线接入点", "access point", "wireless ap"),
    "industrial_gateway": ("工业网关", "industrial gateway"),
    "sd_wan": ("sd-wan", "sd wan"),
    "security_gateway": ("安全网关", "security gateway"),
    "software": ("软件", "software", "app", "application"),
}


class RetrievalService:
    def __init__(
        self,
        embedder: Optional[EmbeddingService] = None,
        section_repository: RegulationSectionRepository = RegulationSectionRepository,
        chunk_repository: RegulationChunkRepository = RegulationChunkRepository,
        spec_repository: RegulationSpecRequirementRepository = RegulationSpecRequirementRepository,
    ):
        self._embedder = embedder or EmbeddingService()
        if section_repository is RegulationSectionRepository and hasattr(chunk_repository, "section_search"):
            section_repository = chunk_repository
        self._section_repository = section_repository
        self._chunk_repository = chunk_repository
        self._spec_repository = spec_repository

    def retrieve(
        self,
        question: str,
        country_code: Optional[str] = None,
        product_code: Optional[str] = None,
        document_id: Optional[str] = None,
        verified_only: bool = True,
        regime_category: Optional[str] = None,
        top_k: int = 6,
    ) -> Dict[str, List[Dict]]:
        requested_document_id = document_id
        if document_id and hasattr(self._chunk_repository, "resolve_ready_document_scope"):
            document_id = self._chunk_repository.resolve_ready_document_scope(document_id)

        inferred_country_code = self._infer_country_code(question) if not country_code else None
        effective_country_code = country_code or inferred_country_code
        inferred_product_code = self._infer_product_code(question) if not product_code else None
        effective_product_code = product_code or inferred_product_code

        section_hits = self._call_search(
            self._section_repository.section_search,
            question=question,
            country_code=effective_country_code,
            document_id=document_id,
            verified_only=verified_only,
            regime_category=regime_category,
            limit=10,
        )
        expanded_question = self._expand_query_for_english_corpus(question)
        keyword_query = self._keyword_query_for_english_corpus(question)
        spec_hits = self._spec_repository.search_for_rag(
            question=expanded_question,
            country_code=effective_country_code,
            product_code=effective_product_code,
            document_id=document_id,
            verified_only=verified_only,
            limit=20,
        )
        spec_evidence_hits = self._build_spec_evidence_hits(spec_hits)
        query_vector = self._embedder.embed_texts([expanded_question])[0]
        vector_hits = self._call_search(
            self._chunk_repository.vector_search,
            query_vector=query_vector,
            country_code=effective_country_code,
            document_id=document_id,
            verified_only=verified_only,
            regime_category=regime_category,
            limit=20,
        )
        keyword_hits = self._call_search(
            self._chunk_repository.keyword_search,
            keyword=keyword_query,
            country_code=effective_country_code,
            document_id=document_id,
            verified_only=verified_only,
            regime_category=regime_category,
            limit=20,
        )
        merged = self._merge_hits(
            section_hits,
            vector_hits,
            keyword_hits,
            spec_evidence_hits,
            top_k=top_k,
            question=question,
        )
        related_records = self._find_related_records(
            merged,
            effective_country_code,
            effective_product_code,
            verified_only=verified_only,
        )
        trace = {
            "grounding_mode": "verified_local_corpus" if verified_only else "mixed_corpus",
            "verified_only": verified_only,
            "filters": {
                "country_code": effective_country_code,
                "requested_country_code": country_code,
                "inferred_country_code": inferred_country_code,
                "product_code": product_code,
                "inferred_product_code": inferred_product_code,
                "effective_product_code": effective_product_code,
                    "document_id": document_id,
                    "requested_document_id": requested_document_id,
                    "regime_category": regime_category,
                },
            "retrieval_counts": {
                "section_hits": len(section_hits),
                "spec_hits": len(spec_hits),
                "spec_evidence_hits": len(spec_evidence_hits),
                "vector_hits": len(vector_hits),
                "keyword_hits": len(keyword_hits),
                "merged_hits": len(merged),
                "related_records": len(related_records),
            },
        }
        return {"hits": merged, "related_records": related_records, "trace": trace}

    @staticmethod
    def _call_search(search_func, **kwargs):
        try:
            return search_func(**kwargs)
        except TypeError as exc:
            if "regime_category" not in kwargs or "regime_category" not in str(exc):
                raise
            compatible_kwargs = dict(kwargs)
            compatible_kwargs.pop("regime_category", None)
            return search_func(**compatible_kwargs)

    def _build_spec_evidence_hits(self, spec_hits: List[Dict]) -> List[Dict]:
        if not spec_hits or not hasattr(self._chunk_repository, "list_by_ids"):
            return []
        chunk_ids = []
        for spec in spec_hits:
            for chunk_id in self._normalize_source_chunk_ids(spec.get("source_chunk_ids")):
                chunk_id = str(chunk_id)
                if chunk_id not in chunk_ids:
                    chunk_ids.append(chunk_id)
        chunks = self._chunk_repository.list_by_ids(chunk_ids) if chunk_ids else []
        chunk_map = {str(chunk.get("id")): chunk for chunk in chunks}
        rows: List[Dict] = []
        for spec in spec_hits:
            spec_rows: List[Dict] = []
            for chunk_id in self._normalize_source_chunk_ids(spec.get("source_chunk_ids")):
                chunk = chunk_map.get(str(chunk_id))
                if not chunk:
                    continue
                spec_rows.append(chunk)
            if not spec_rows and hasattr(self._chunk_repository, "list_by_document_pages"):
                pages = self._parse_source_pages(spec.get("source_pages"))
                if pages:
                    spec_rows = self._chunk_repository.list_by_document_pages(
                        str(spec.get("document_id")),
                        pages,
                        limit=3,
                    )
            for chunk in spec_rows:
                rows.append({
                    **chunk,
                    "spec_score": float(spec.get("spec_score") or 1.0),
                    "spec_context": self._format_spec_context(spec),
                })
        return rows

    def _normalize_source_chunk_ids(self, value) -> List[str]:
        if not value:
            return []
        if isinstance(value, str):
            if value.strip() in {"{}", "[]"}:
                return []
            return re.findall(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                value,
            )
        return [str(item) for item in value if item]

    def _parse_source_pages(self, value) -> List[int]:
        if not value:
            return []
        pages: List[int] = []
        for start, end in re.findall(r"(\d{1,4})(?:\s*[-–]\s*(\d{1,4}))?", str(value)):
            start_no = int(start)
            end_no = int(end or start)
            if end_no < start_no:
                end_no = start_no
            pages.extend(range(start_no, min(end_no, start_no + 10) + 1))
        deduped: List[int] = []
        for page in pages:
            if page not in deduped:
                deduped.append(page)
        return deduped[:20]

    def _format_spec_context(self, spec: Dict) -> Dict:
        fields = (
            "id",
            "req_id",
            "module_zh",
            "module_en",
            "title_zh",
            "title_en",
            "description_zh",
            "description_en",
            "verification_method_zh",
            "verification_method_en",
            "mandatory",
            "priority",
            "regulation_clause",
            "source_pages",
        )
        return {field: spec.get(field) for field in fields if spec.get(field)}

    def _expand_query_for_english_corpus(self, question: str) -> str:
        if self._looks_like_network_device_query(question):
            return (
                f"{question}\n"
                "US NIAP Common Criteria collaborative Protection Profile for Network Devices "
                "security functional requirements router switch network device"
            )
        return question

    def _keyword_query_for_english_corpus(self, question: str) -> str:
        if self._looks_like_network_device_query(question):
            return "Protection Profile Network Devices security functional requirements"
        if self._looks_like_cn_product_certification_query(question):
            return "网络关键设备 专用网络安全产品 认证 检测 目录 强制 安全"
        if self._looks_like_psti_query(question):
            return "Product Security security requirements"
        return question

    def _looks_like_network_device_query(self, question: str) -> bool:
        lowered = (question or "").lower()
        markers = (
            "交换机",
            "路由器",
            "网络设备",
            "network device",
            "router",
            "switch",
        )
        return any(marker in lowered for marker in markers)

    def _looks_like_cn_product_certification_query(self, question: str) -> bool:
        lowered = (question or "").lower()
        return any(
            marker in lowered
            for marker in (
                "网络关键设备",
                "专用网络安全产品",
                "critical network equipment",
                "specialized cybersecurity products",
            )
        )

    def _looks_like_psti_query(self, question: str) -> bool:
        lowered = (question or "").lower()
        return any(
            marker in lowered
            for marker in (
                "psti",
                "product security and telecommunications infrastructure",
                "connectable product",
            )
        )

    def _infer_product_code(self, question: str) -> Optional[str]:
        lowered = (question or "").lower()
        for product_code, hints in _PRODUCT_QUERY_HINTS.items():
            if any(hint in lowered for hint in hints):
                return product_code
        return None

    def _infer_country_code(self, question: str) -> Optional[str]:
        text = question or ""
        lowered = text.lower()
        for code, hints in self._country_hints():
            for hint in hints:
                if not hint:
                    continue
                if self._contains_cjk(hint):
                    if hint in text:
                        return code
                elif re.search(rf"(?<![a-z0-9]){re.escape(hint.lower())}(?![a-z0-9])", lowered):
                    return code
        return None

    @staticmethod
    @lru_cache(maxsize=1)
    def _country_hints() -> tuple[tuple[str, tuple[str, ...]], ...]:
        aliases = {
            "GB": ("UK", "U.K.", "Britain", "英国"),
            "US": ("USA", "U.S.", "United States of America", "美国"),
            "EU": ("European Union", "欧盟"),
        }
        try:
            with get_cursor() as cur:
                cur.execute("SELECT code, name_zh, name_en FROM countries WHERE enabled=TRUE")
                rows = [dict(row) for row in cur.fetchall()]
        except Exception:
            rows = []
        items: List[tuple[str, tuple[str, ...]]] = []
        for row in rows:
            code = str(row.get("code") or "").upper()
            hints = [
                code,
                str(row.get("name_zh") or ""),
                str(row.get("name_en") or ""),
                *aliases.get(code, ()),
            ]
            deduped: List[str] = []
            for hint in hints:
                cleaned = hint.strip()
                if cleaned and cleaned not in deduped:
                    deduped.append(cleaned)
            items.append((code, tuple(sorted(deduped, key=len, reverse=True))))
        if not items:
            items = [(code, tuple(values)) for code, values in aliases.items()]
        return tuple(sorted(items, key=lambda item: max((len(v) for v in item[1]), default=0), reverse=True))

    @staticmethod
    def _contains_cjk(value: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", value or ""))

    def _merge_hits(
        self,
        section_hits: List[Dict],
        vector_hits: List[Dict],
        keyword_hits: List[Dict],
        spec_hits: List[Dict],
        top_k: int,
        question: str = "",
    ) -> List[Dict]:
        merged: Dict[tuple, Dict] = {}
        for row in section_hits:
            key = (row["document_id"], row["chunk_index"])
            merged[key] = {
                **row,
                "section_score": float(row.get("section_score", 0)),
                "spec_score": 0.0,
                "vector_score": 0.0,
                "keyword_score": 0.0,
                "doc_score": 0.0,
            }
        for row in spec_hits:
            key = (row["document_id"], row["chunk_index"])
            current = merged.setdefault(
                key,
                {
                    **row,
                    "section_score": 0.0,
                    "spec_score": 0.0,
                    "vector_score": 0.0,
                    "keyword_score": 0.0,
                    "doc_score": 0.0,
                },
            )
            current["spec_score"] = max(float(row.get("spec_score", 0)), current["spec_score"])
            current.setdefault("spec_context", row.get("spec_context"))
            current.setdefault("content", row["content"])
            current.setdefault("document_name", row["document_name"])
            current.setdefault("country_code", row["country_code"])
            current.setdefault("page_from", row["page_from"])
            current.setdefault("page_to", row["page_to"])
            current.setdefault("clause_ref", row.get("clause_ref"))
        for row in vector_hits:
            key = (row["document_id"], row["chunk_index"])
            current = merged.setdefault(
                key,
                {
                    **row,
                    "section_score": 0.0,
                    "spec_score": 0.0,
                    "vector_score": 0.0,
                    "keyword_score": 0.0,
                    "doc_score": 0.0,
                },
            )
            current["vector_score"] = max(float(row.get("vector_score", 0)), current["vector_score"])
        for row in keyword_hits:
            key = (row["document_id"], row["chunk_index"])
            current = merged.setdefault(
                key,
                {
                    **row,
                    "section_score": 0.0,
                    "spec_score": 0.0,
                    "vector_score": 0.0,
                    "keyword_score": 0.0,
                    "doc_score": 0.0,
                },
            )
            current["keyword_score"] = max(float(row.get("keyword_score", 0)), current["keyword_score"])
            current.setdefault("content", row["content"])
            current.setdefault("document_name", row["document_name"])
            current.setdefault("country_code", row["country_code"])
            current.setdefault("page_from", row["page_from"])
            current.setdefault("page_to", row["page_to"])
            current.setdefault("clause_ref", row.get("clause_ref"))
        items = list(merged.values())
        for item in items:
            freshness_score = 0.1 if item.get("document_name") else 0.0
            item["doc_score"] = max(
                float(item.get("doc_score") or 0.0),
                self._document_relevance_boost(question, item),
            )
            item["score"] = (
                item["section_score"] * 1.2
                + item["spec_score"] * 1.0
                + item["vector_score"] * 0.6
                + item["keyword_score"] * 0.3
                + item["doc_score"]
                + freshness_score
            )
        return sorted(items, key=lambda item: item["score"], reverse=True)[:top_k]

    def _document_relevance_boost(self, question: str, item: Dict) -> float:
        haystack = " ".join(
            str(item.get(field) or "")
            for field in ("document_name", "section_path", "clause_ref", "content")
        ).lower()
        score = 0.0
        if self._looks_like_network_device_query(question):
            if "niap" in haystack:
                score += 0.4
            if "protection profile" in haystack:
                score += 0.35
            if "network device" in haystack or "network devices" in haystack:
                score += 0.25
            if "security functional requirements" in haystack:
                score += 0.25
            if any(marker in (question or "").lower() for marker in ("交换机", "switch")) and (
                "cyber trust mark" in haystack or "iot label" in haystack or "iot labeling" in haystack
            ):
                score -= 0.25
        if self._looks_like_cn_product_certification_query(question):
            if "critical network equipment" in haystack or "网络关键设备" in haystack:
                score += 0.35
            if "specialized cybersecurity products" in haystack or "专用网络安全产品" in haystack:
                score += 0.35
            if "certification" in haystack or "认证" in haystack:
                score += 0.2
            if "catalogue" in haystack or "目录" in haystack:
                score += 0.15
        if self._looks_like_psti_query(question):
            if "psti" in haystack:
                score += 0.35
            if "product security and telecommunications infrastructure" in haystack:
                score += 0.35
            if "connectable product" in haystack or "connectable products" in haystack:
                score += 0.2
            if "default password" in haystack or "vulnerability" in haystack or "security update" in haystack:
                score += 0.15
        return max(-0.3, min(score, 1.0))

    def _find_related_records(
        self,
        hits: List[Dict],
        country_code: Optional[str],
        product_code: Optional[str],
        verified_only: bool,
    ) -> List[Dict]:
        record_ids = [hit["compliance_id"] for hit in hits if hit.get("compliance_id")]
        if record_ids:
            if verified_only:
                return ComplianceIndexRepository.list_by_ids(record_ids, verified_only=True)
            return ComplianceRepository.list_by_ids(record_ids)
        if country_code and product_code:
            if verified_only:
                return ComplianceIndexRepository.list_by_product(product_code, country_code, verified_only=True, limit=5)
            return ComplianceRepository.list_by_product(product_code, country_code)[:5]
        if country_code:
            if verified_only:
                return ComplianceIndexRepository.list_by_country(country_code, verified_only=True, limit=5)
            return ComplianceRepository.list_by_country(country_code)[:5]
        return []
