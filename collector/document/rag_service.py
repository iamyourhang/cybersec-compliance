"""
collector/document/rag_service.py
统一编排 RAG 检索与回答。
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from collector.document.answer_service import AnswerService
from collector.document.retrieval_service import RetrievalService
from database.repository import ComplianceIndexRepository, PRODUCT_REGIME_CATEGORY


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class AskPayload(BaseModel):
    question: str
    country_code: Optional[str] = None
    product_code: Optional[str] = None
    document_id: Optional[str] = None
    top_k: int = 6
    verified_only: bool = True
    regime_category: Optional[str] = None
    history: List[HistoryMessage] = Field(default_factory=list)


class RAGService:
    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        answer_service: Optional[AnswerService] = None,
    ):
        self._retrieval = retrieval_service or RetrievalService()
        self._answer = answer_service or AnswerService()

    def ask(self, request: AskPayload):
        if request.verified_only and not request.document_id and self._looks_like_inventory_question(request.question):
            inventory = self._answer_inventory_question(request)
            if inventory:
                return inventory

        retrieval = self._retrieval.retrieve(
            question=request.question,
            country_code=request.country_code,
            product_code=request.product_code,
            document_id=request.document_id,
            verified_only=request.verified_only,
            regime_category=request.regime_category,
            top_k=request.top_k,
        )
        return self._answer.answer(
            question=request.question,
            hits=retrieval["hits"],
            related_records=retrieval["related_records"],
            history=[item.model_dump() for item in request.history],
            trace=retrieval.get("trace"),
        )

    def _looks_like_inventory_question(self, question: str) -> bool:
        text = question or ""
        lowered = text.lower()
        has_list_intent = any(marker in text for marker in ("有哪些", "清单", "列表", "分类", "已验证", "当前")) or any(
            marker in lowered for marker in ("list", "inventory", "verified")
        )
        has_compliance_scope = any(marker in text for marker in ("法规", "认证", "标准", "要求", "制度")) or any(
            marker in lowered for marker in ("regulation", "certification", "standard", "requirements")
        )
        return has_list_intent and has_compliance_scope

    def _answer_inventory_question(self, request: AskPayload) -> Optional[dict]:
        country_code = request.country_code or self._safe_infer_country_code(request.question)
        product_code = request.product_code or self._safe_infer_product_code(request.question)
        if not country_code:
            return None
        result = ComplianceIndexRepository.list_filtered(
            country_code=country_code,
            product_code=product_code,
            status="active",
            authenticity_status="verified",
            regime_category=PRODUCT_REGIME_CATEGORY if product_code else None,
            include_inherited=True,
            include_suspicious=False,
            limit=50,
            offset=0,
            sort_by="mandatory",
            sort_order="asc",
        )
        items = result.get("items") or []
        if not items:
            return None

        answer = self._format_inventory_answer(country_code, product_code, items)
        citations = [self._format_inventory_citation(item) for item in items[:3]]
        related_records = [
            {
                "id": item.get("compliance_id") or item.get("id"),
                "name": item.get("name"),
                "entry_type": item.get("entry_type"),
                "country_code": item.get("country_code"),
            }
            for item in items[:10]
        ]
        return {
            "status": "answered",
            "answer": answer,
            "citations": citations,
            "related_records": related_records,
            "next_actions": [
                "点击条目详情查看官方链接、证据备注和原文工件。",
                "如需解释某一项具体要求，可基于该条目继续追问。",
                "如需导出正式清单，请使用后台 Excel 导出，默认同样只包含 verified 数据。",
            ],
            "trace": {
                "grounding_mode": "verified_read_model_inventory",
                "verified_only": True,
                "filters": {
                    "country_code": country_code,
                    "requested_country_code": request.country_code,
                    "inferred_country_code": None if request.country_code else country_code,
                    "product_code": request.product_code,
                    "inferred_product_code": None if request.product_code else product_code,
                    "effective_product_code": product_code,
                    "document_id": None,
                    "requested_document_id": request.document_id,
                },
                "retrieval_counts": {
                    "inventory_records": len(items),
                    "merged_hits": len(items),
                    "related_records": len(related_records),
                },
            },
        }

    def _safe_infer_country_code(self, question: str) -> Optional[str]:
        infer = getattr(self._retrieval, "_infer_country_code", None)
        return infer(question) if callable(infer) else None

    def _safe_infer_product_code(self, question: str) -> Optional[str]:
        infer = getattr(self._retrieval, "_infer_product_code", None)
        return infer(question) if callable(infer) else None

    def _format_inventory_answer(self, country_code: str, product_code: Optional[str], items: List[dict]) -> str:
        product_items = [item for item in items if item.get("regime_category") == PRODUCT_REGIME_CATEGORY]
        general_items = [item for item in items if item.get("regime_category") != PRODUCT_REGIME_CATEGORY]
        scoped_items = product_items if not product_code else items
        mandatory_items = [item for item in scoped_items if item.get("mandatory") == "mandatory"]
        voluntary_items = [item for item in scoped_items if item.get("mandatory") in {"voluntary", "recommended"}]
        other_items = [item for item in scoped_items if item not in mandatory_items and item not in voluntary_items]
        scope = f"{country_code}"
        if product_code:
            scope += f" / 产品={product_code}"
        product_count = len(scoped_items) if product_code else len(product_items)
        general_count = 0 if product_code else len(general_items)
        lines = [
            (
                f"以下为当前 verified 知识库中 {scope} 的清单；"
                f"产品级制度 {product_count} 条，"
                f"通用网络安全背景 {general_count} 条。"
            ),
            "",
            "产品级强制类：",
        ]
        lines.extend(self._format_inventory_group(mandatory_items) or ["- 当前 verified 记录中未列出强制类。"])
        lines.extend(["", "产品级自愿/推荐类："])
        lines.extend(self._format_inventory_group(voluntary_items) or ["- 当前 verified 记录中未列出自愿/推荐类。"])
        if other_items:
            lines.extend(["", "产品级其他/未标明强制性："])
            lines.extend(self._format_inventory_group(other_items))
        if general_items and not product_code:
            lines.extend(["", "通用网络安全背景（不直接等同于产品准入/认证要求）："])
            lines.extend(self._format_inventory_group(general_items[:8]))
        lines.extend([
            "",
            "依据：以上每条均来自 compliance_index 中 authenticity_status=verified 的正式读模型记录，并保留官方来源链接；候选、可疑和隔离数据未参与本次回答。",
        ])
        return "\n".join(lines)

    def _format_inventory_group(self, items: List[dict]) -> List[str]:
        entry_type_map = {"regulation": "法规", "certification": "认证", "standard": "标准"}
        lines = []
        for item in items:
            products = "、".join(item.get("applicable_products") or []) or "见官方范围"
            effective = f"，生效日期：{item.get('effective_date')}" if item.get("effective_date") else ""
            issuer = f"，发布/主管机构：{item.get('issuing_body')}" if item.get("issuing_body") else ""
            summary = f"。摘要：{item.get('summary')}" if item.get("summary") else ""
            scope = ""
            if item.get("scope_origin") == "inherited":
                scope = f"，{item.get('inherited_from_code') or item.get('country_code')} 层面适用"
            official_url = item.get("official_url") or "未记录"
            lines.append(
                f"- {item.get('name')}（{entry_type_map.get(item.get('entry_type'), item.get('entry_type') or '条目')}，"
                f"适用产品：{products}{issuer}{effective}{scope}）。依据：{official_url}{summary}"
            )
        return lines

    def _format_inventory_citation(self, item: dict) -> dict:
        return {
            "document_id": item.get("document_id") or item.get("compliance_id") or item.get("id"),
            "document_name": item.get("name"),
            "page_from": None,
            "page_to": None,
            "clause_ref": "verified read model",
            "excerpt": (
                f"{item.get('name')} | {item.get('entry_type')} | {item.get('mandatory')} | "
                f"{item.get('issuing_body') or ''} | {item.get('official_url') or ''}"
            )[:240],
            "country_code": item.get("country_code"),
        }
