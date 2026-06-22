"""
collector/document/answer_service.py
严格引用回答生成。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from collector.providers.channel_router import ChannelRouter, get_channel_router


SummaryFn = Callable[[str, List[Dict], List[Dict], List[Dict]], str]


class AnswerService:
    def __init__(
        self,
        summarizer: Optional[SummaryFn] = None,
        router: Optional[ChannelRouter] = None,
    ):
        self._summarizer = summarizer or self._default_summarizer
        self._router = router or get_channel_router()

    def answer(
        self,
        question: str,
        hits: List[Dict],
        related_records: List[Dict],
        history: Optional[List[Dict]] = None,
        trace: Optional[Dict] = None,
    ) -> Dict:
        threshold = self._strong_hit_threshold(trace)
        strong_hits = [
            hit
            for hit in hits
            if float(hit.get("score", 0)) >= threshold and self._has_evidence_signal(hit)
        ]
        if len(strong_hits) < 2:
            return self._insufficient(trace)

        answer = self._summarizer(question, strong_hits[:6], related_records, history or [])
        if not answer or not answer.strip():
            return self._insufficient(trace)
        if self._is_insufficient_answer(answer):
            return self._insufficient(trace)

        result = {
            "status": "answered",
            "answer": answer.strip(),
            "citations": [self._format_citation(hit) for hit in strong_hits[:3]],
            "related_records": related_records,
            "next_actions": [
                "展开右侧证据面板，复核条款号和页码。",
                "如需形成规格条目，可在法规原文页对该文档生成规格。",
                "若要提高确定性，可进一步限定到单一法规文档后重问。",
            ],
        }
        if trace is not None:
            result["trace"] = trace
        return result

    def _strong_hit_threshold(self, trace: Optional[Dict]) -> float:
        filters = (trace or {}).get("filters") or {}
        if filters.get("document_id"):
            # A user-selected verified document is a tighter evidence boundary; vector-only
            # matches in multilingual law text should not be discarded as aggressively.
            return 0.3
        counts = (trace or {}).get("retrieval_counts") or {}
        if (trace or {}).get("verified_only") and int(counts.get("merged_hits") or 0) >= 2:
            # Verified country-level searches often mix Chinese questions with English
            # source PDFs. Keep the guard, but allow multiple official chunks through
            # to the strict citation prompt instead of dropping all low-ranked evidence.
            return 0.1
        return 0.6

    def _has_evidence_signal(self, hit: Dict) -> bool:
        """Do not treat freshness-only rows as legal evidence."""
        seen_score_component = False
        for field in ("section_score", "spec_score", "vector_score", "keyword_score", "doc_score"):
            if field in hit:
                seen_score_component = True
            try:
                if float(hit.get(field) or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        return not seen_score_component

    def _default_summarizer(self, question: str, hits: List[Dict], related_records: List[Dict], history: List[Dict]) -> str:
        evidence = "\n\n".join(
            self._format_evidence_block(i, hit)
            for i, hit in enumerate(hits[:6])
        )
        conversation = "\n".join(
            f"- {item['role']}: {str(item['content']).strip()[:300]}"
            for item in history[-6:]
            if item.get("role") in {"user", "assistant"} and str(item.get("content", "")).strip()
        ) or "无"
        related = "\n".join(
            f"- {record['name']} ({record['entry_type']}, {record['country_code']})"
            for record in related_records[:6]
        ) or "无"
        prompt = (
            "你是一名严格引用的法规问答助手。"
            "只能基于提供的证据作答，禁止补充证据中没有的法律结论。"
            "禁止把候选、可疑、联网搜索或训练记忆当成证据。"
            "如果证据中带有“规格库提示”，它只能用于组织答案和提炼产品要求；"
            "最终结论仍必须由同一证据块中的官方原文片段支持。"
            "如果用户用中文产品词提问，例如交换机、路由器、网络设备，而证据原文使用 Network Device、"
            "Router、Switch、Protection Profile 等英文范围表达，可以在答案中做术语映射，"
            "但必须明确限定为“当前证据支持的范围”，不得扩大成所有美国市场准入强制要求。"
            "如果证据不足，请只回答：现有原文证据不足以确认该结论。\n\n"
            f"问题：{question}\n\n"
            f"最近对话上下文（仅用于理解指代，不得突破证据边界）：\n{conversation}\n\n"
            f"关联结构化摘要：\n{related}\n\n"
            f"证据片段：\n{evidence}"
        )
        response = self._router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
            enable_web_search=False,
        )
        return response.content

    def _format_evidence_block(self, index: int, hit: Dict) -> str:
        spec = hit.get("spec_context") or {}
        spec_text = ""
        if spec:
            spec_text = (
                "\n规格库提示（派生自原文，用于定位产品要求，不可单独作为结论）："
                f"\n- 要求ID：{spec.get('req_id') or '无'}"
                f"\n- 标题：{spec.get('title_zh') or spec.get('title_en') or '无'}"
                f"\n- 要求：{spec.get('description_zh') or spec.get('description_en') or '无'}"
                f"\n- 验证方法：{spec.get('verification_method_zh') or spec.get('verification_method_en') or '无'}"
            )
        return (
            f"[证据{index+1}] 文档={hit['document_name']} 页码={hit['page_from']}-{hit['page_to']} "
            f"条款={hit.get('clause_ref') or '无'}{spec_text}\n"
            f"官方原文片段：\n{hit['content']}"
        )

    def _is_insufficient_answer(self, answer: str) -> bool:
        normalized = (answer or "").strip()
        if normalized.startswith("现有原文证据不足以确认该结论"):
            return True
        return normalized in {
            "现有原文证据不足以确认该结论。",
            "现有原文证据不足以确认该结论",
        }

    def _format_citation(self, hit: Dict) -> Dict:
        return {
            "document_id": hit["document_id"],
            "document_name": hit["document_name"],
            "page_from": hit["page_from"],
            "page_to": hit["page_to"],
            "clause_ref": hit.get("clause_ref"),
            "excerpt": hit["content"][:240],
            "country_code": hit["country_code"],
        }

    def _insufficient(self, trace: Optional[Dict] = None) -> Dict:
        result = {
            "status": "insufficient_evidence",
            "answer": "现有原文证据不足以确认该结论。",
            "citations": [],
            "related_records": [],
            "next_actions": [
                "补充国家、产品或限定具体法规文档后再提问。",
                "确认该问题对应的官方原文是否已下载并完成索引。",
                "如果你在问适用性或强制性结论，请优先查看条款原文。",
            ],
        }
        if trace is not None:
            result["trace"] = trace
        return result
