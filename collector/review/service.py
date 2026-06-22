from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from collections import Counter
from typing import Any, Dict, Optional

import httpx

from collector.parsers.compliance_parser import extract_json_from_text
from collector.providers.channel_repository import _normalize_openai_base_url
from collector.providers.channel_router import ChannelRouter, get_channel_router
from config.settings import get_settings
from database.repository import (
    CanonicalRequirementRepository,
    ComplianceIndexRepository,
    ComplianceRepository,
    ReviewCaseRepository,
    SourceArtifactRepository,
    SourceRecordRepository,
)


class AuthenticityReviewService:
    def __init__(self, router: Optional[ChannelRouter] = None, verification_agent: Optional[Any] = None):
        self._router = router or get_channel_router()
        self._verification_agent = verification_agent or AuthenticityVerificationAgent()

    def list_cases(
        self,
        current_status: Optional[str] = None,
        country_code: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        items = ReviewCaseRepository.list_cases(
            current_status=current_status,
            country_code=country_code,
            limit=limit,
        )
        return {"items": items, "total": len(items)}

    def apply_decision(
        self,
        case_id: str,
        decision: Dict[str, Any],
        checked_by: str,
    ) -> Dict[str, Any]:
        case = ReviewCaseRepository.get_by_id(case_id)
        if not case:
            raise ValueError("review case 不存在")
        record = ComplianceRepository.get_by_id(str(case["compliance_id"]))
        if not record:
            raise ValueError("关联条目不存在")

        ComplianceRepository.set_authenticity_review(
            str(record["id"]),
            authenticity_status=decision["authenticity_status"],
            risk_score=int(decision["risk_score"]),
            reasons=decision["reasons"],
            checked_by=checked_by,
            evidence=decision["evidence_note"],
        )

        update_payload: Dict[str, Any] = {"verified": decision["authenticity_status"] == "verified"}
        if decision.get("source_download_status") is not None:
            update_payload["source_download_status"] = decision["source_download_status"]
        if decision.get("source_download_error") is not None or decision.get("source_download_status") == "failed":
            update_payload["source_download_error"] = (decision.get("source_download_error") or "")[:1000] or None
        ComplianceRepository.update(str(record["id"]), update_payload, force=True)

        review_case_id = ReviewCaseRepository.apply_decision(
            str(record["id"]),
            authenticity_status=decision["authenticity_status"],
            risk_score=int(decision["risk_score"]),
            reasons=decision["reasons"],
            evidence_note=decision["evidence_note"],
            checked_by=checked_by,
            source_download_status=decision.get("source_download_status"),
            source_download_error=decision.get("source_download_error"),
        )

        CanonicalRequirementRepository.upsert_from_compliance(
            {**dict(record), **update_payload},
            verification_status="verified" if decision["authenticity_status"] == "verified" else "candidate",
        )
        refreshed = ComplianceRepository.get_by_id(str(record["id"])) or {**dict(record), **update_payload}
        ComplianceIndexRepository.refresh_for_compliance(dict(refreshed))
        updated_case = ReviewCaseRepository.get_by_id(review_case_id)
        return dict(updated_case) if updated_case else {"id": review_case_id, "current_status": decision["authenticity_status"]}

    def generate_ai_assist(self, case_id: str) -> Dict[str, Any]:
        case = ReviewCaseRepository.get_by_id(case_id)
        if not case:
            raise ValueError("review case 不存在")
        record = ComplianceRepository.get_by_id(str(case["compliance_id"]))
        if not record:
            raise ValueError("关联条目不存在")
        evidence = self.get_evidence(str(case["compliance_id"]))
        prompt = self._build_ai_assist_prompt(dict(record), case, evidence)

        try:
            response = self._call_ai_assist_model(prompt)
            payload = json.loads(extract_json_from_text(response.content))
            if not isinstance(payload, dict):
                raise ValueError("AI 输出格式错误")
        except Exception:
            payload = self._fallback_ai_assist(dict(record), case, evidence)

        payload["case_id"] = case_id
        return payload

    def dry_run_authenticity_verification(
        self,
        current_status: str = "suspicious",
        country_code: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        records = ComplianceIndexRepository.list_for_verification(
            current_status=current_status,
            country_code=country_code,
            limit=limit,
        )
        items = []
        counts: Counter[str] = Counter()
        for record in records:
            try:
                suggestion = self._verification_agent.verify(record)
            except Exception as exc:
                suggestion = {
                    "suggested_status": "error",
                    "official_evidence_found": False,
                    "official_url": None,
                    "artifact_url": None,
                    "evidence_summary": f"AI 校验失败: {exc}",
                    "gaps": ["需要人工复核"],
                    "confidence": 0.0,
                }
            status = str(suggestion.get("suggested_status") or "error")
            counts[status] += 1
            items.append(
                {
                    "compliance_id": record.get("compliance_id"),
                    "country_code": record.get("country_code"),
                    "name": record.get("name"),
                    "entry_type": record.get("entry_type"),
                    "mandatory": record.get("mandatory"),
                    "current_status": current_status,
                    "official_url": record.get("official_url"),
                    "suggestion": suggestion,
                }
            )
        return {
            "dry_run": True,
            "current_status": current_status,
            "country_code": country_code,
            "sample_size": len(items),
            "status_counts": dict(counts),
            "items": items,
        }

    def _call_ai_assist_model(self, prompt: str):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self._router.chat,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=700,
            enable_web_search=False,
        )
        try:
            return future.result(timeout=12)
        except FuturesTimeoutError:
            future.cancel()
            raise
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def register_manual_source(
        self,
        record: Dict[str, Any],
        ingest_result: Dict[str, Any],
        official_url: str,
        evidence_note: str,
        checked_by: str,
    ) -> Dict[str, Any]:
        source_record = SourceRecordRepository.get_by_compliance_id(str(record["id"]))
        source_record_id = source_record["id"] if source_record else None
        artifact_id = SourceArtifactRepository.upsert_for_compliance(
            str(record["id"]),
            official_url=official_url,
            artifact_url=ingest_result.get("source_url"),
            artifact_type=ingest_result.get("file_type"),
            artifact_sha256=ingest_result.get("sha256"),
            download_status="downloaded",
            download_error=None,
            document_id=ingest_result.get("doc_id"),
            source_record_id=source_record_id,
        )

        ComplianceRepository.update(
            str(record["id"]),
            {
                "verified": True,
                "official_url": official_url,
                "source_document_id": ingest_result.get("doc_id"),
                "source_artifact_url": ingest_result.get("source_url"),
                "source_artifact_type": ingest_result.get("file_type"),
                "source_artifact_sha256": ingest_result.get("sha256"),
                "source_download_status": "downloaded",
                "source_download_error": None,
            },
            force=True,
        )
        ComplianceRepository.set_authenticity_review(
            str(record["id"]),
            authenticity_status="verified",
            risk_score=0,
            reasons=["manual_source_verified", "official_artifact_downloaded"],
            checked_by=checked_by,
            evidence=evidence_note,
        )
        refreshed = ComplianceRepository.get_by_id(str(record["id"])) or dict(record)
        canonical_id = CanonicalRequirementRepository.upsert_from_compliance(
            dict(refreshed),
            verification_status="verified",
            source_record_id=source_record_id,
            source_artifact_id=artifact_id,
            document_id=ingest_result.get("doc_id"),
        )
        review_case_id = ReviewCaseRepository.apply_decision(
            str(record["id"]),
            authenticity_status="verified",
            risk_score=0,
            reasons=["manual_source_verified", "official_artifact_downloaded"],
            evidence_note=evidence_note,
            checked_by=checked_by,
            source_download_status="downloaded",
            source_download_error=None,
            canonical_requirement_id=canonical_id,
            source_record_id=source_record_id,
        )
        ComplianceIndexRepository.refresh_for_compliance(dict(refreshed))
        return {
            "canonical_requirement_id": canonical_id,
            "review_case_id": review_case_id,
            "source_artifact_id": artifact_id,
        }

    def get_evidence(self, entity_id: str) -> Dict[str, Any]:
        review_case = ReviewCaseRepository.get_by_compliance_id(entity_id) or ReviewCaseRepository.get_by_id(entity_id)
        if not review_case:
            return {"entity_id": entity_id, "review_case": None, "events": [], "artifacts": []}
        return {
            "entity_id": entity_id,
            "review_case": review_case,
            "events": ReviewCaseRepository.list_events(str(review_case["id"])),
            "artifacts": SourceArtifactRepository.list_by_entity(entity_id),
        }

    def _build_ai_assist_prompt(self, record: Dict[str, Any], case: Dict[str, Any], evidence: Dict[str, Any]) -> str:
        artifact_lines = "\n".join(
            f"- type={artifact.get('artifact_type') or 'artifact'} "
            f"status={artifact.get('download_status') or 'pending'} "
            f"official={artifact.get('official_url') or '—'} "
            f"artifact={artifact.get('artifact_url') or '—'} "
            f"error={artifact.get('download_error') or '—'}"
            for artifact in evidence.get("artifacts", [])[:8]
        ) or "- 无已挂载工件"
        event_lines = "\n".join(
            f"- {event.get('event_type')} {event.get('from_status') or '—'} -> {event.get('to_status') or '—'}"
            for event in evidence.get("events", [])[:8]
        ) or "- 无审核事件"
        reasons = "\n".join(f"- {reason}" for reason in (case.get("reasons") or [])) or "- 无"
        return (
            "你是一名真实性审核助手。"
            "你的职责是总结当前本地证据、指出还缺什么，不得替系统决定 verified/suspicious/quarantined。"
            "禁止联网，禁止引用训练记忆，只能基于下面提供的本地记录、工件和审核事件。\n\n"
            f"条目名称：{record.get('name')}\n"
            f"国家：{record.get('country_code')}\n"
            f"类型：{record.get('entry_type')}\n"
            f"当前状态：{case.get('current_status')}\n"
            f"风险分：{case.get('risk_score')}\n"
            f"官方链接：{record.get('official_url') or '—'}\n"
            f"现有证据备注：{case.get('evidence_note') or '—'}\n"
            f"现有 reasons：\n{reasons}\n\n"
            f"证据工件：\n{artifact_lines}\n\n"
            f"审核事件：\n{event_lines}\n\n"
            "请输出 JSON 对象，字段固定为：\n"
            "{\n"
            '  "summary": "一句话总结当前证据状态",\n'
            '  "evidence_status": "如 official_program_confirmed / artifact_missing / homepage_only / weak_evidence",\n'
            '  "confirmed_facts": ["已确认事实"],\n'
            '  "gaps": ["仍缺什么证据"],\n'
            '  "recommended_actions": ["下一步人工动作建议"],\n'
            '  "warning": "提醒：AI 仅辅助，不做最终真实性决策"\n'
            "}\n"
            "只输出 JSON。"
        )

    def _fallback_ai_assist(self, record: Dict[str, Any], case: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = evidence.get("artifacts", [])
        official_urls = [artifact.get("official_url") for artifact in artifacts if artifact.get("official_url")]
        evidence_status = "artifact_missing"
        summary = "当前记录缺少可稳定复核的官方原文工件。"
        gaps = ["缺少可稳定访问的官方正文页或官方 PDF"]
        if official_urls:
            evidence_status = "official_page_attached"
            summary = "当前记录已挂官方页面线索，但工件闭环仍不完整。"
            gaps = ["需要补官方 PDF 或可长期复核的稳定工件"]
        if (case.get("source_download_status") or "") == "failed":
            gaps.append("需要记录下载失败原因并区分环境问题与真实缺证")
        return {
            "summary": summary,
            "evidence_status": evidence_status,
            "confirmed_facts": [
                f"当前状态为 {case.get('current_status')}",
                f"现有证据工件 {len(artifacts)} 个",
            ],
            "gaps": gaps,
            "recommended_actions": [
                "补官方正文页或官方 PDF",
                "将下载错误写入 evidence_note，避免与伪造项混淆",
                "若已确认官方项目存在，再通过 manual-source 走正式 verified 链路",
            ],
            "warning": "AI 仅辅助总结证据，不做最终真实性决策；若模型超时或失败，当前结果来自本地兜底摘要。",
        }


class AuthenticityVerificationAgent:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-5.4-mini",
        timeout: int = 120,
        http_client: Optional[httpx.Client] = None,
    ):
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.uniapi.api_key
        self._base_url = _normalize_openai_base_url(base_url or settings.uniapi.base_url).rstrip("/")
        self._model = model
        self._timeout = timeout
        self._http_client = http_client or httpx.Client(timeout=timeout, trust_env=False)

    def verify(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if not self._api_key or not self._base_url:
            raise RuntimeError("UNIAPI_API_KEY 或 UNIAPI_BASE_URL 未配置")
        started = time.time()
        response = self._http_client.post(
            f"{self._base_url}/responses",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "tools": [{"type": "web_search"}],
                "input": self._build_prompt(record),
                "max_output_tokens": 700,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        text = self._extract_text(data)
        payload = json.loads(extract_json_from_text(text))
        if not isinstance(payload, dict):
            raise ValueError("AI 校验输出不是 JSON 对象")
        payload["latency_ms"] = int((time.time() - started) * 1000)
        payload["web_actions"] = self._extract_actions(data)
        return payload

    @staticmethod
    def _build_prompt(record: Dict[str, Any]) -> str:
        return (
            "使用 web_search 对 suspicious/candidate 合规记录做真实性预审，不写库。"
            "必须保守：只确认底层 IEC/ETSI/ISO 标准存在但无法确认本地采纳时，建议 suspicious，不得建议 verified。"
            "只有官方政府、监管机构、官方公报、官方标准/认证机构页面或 PDF 能支持 verified 建议。"
            "如果页面不存在、名称明显不匹配、不是网络安全产品合规/认证/标准，建议 quarantined。\n\n"
            f"国家/地区：{record.get('country_code')}\n"
            f"名称：{record.get('name')}\n"
            f"类型：{record.get('entry_type')}\n"
            f"强制性：{record.get('mandatory')}\n"
            f"候选官方链接：{record.get('official_url') or '无'}\n"
            f"摘要：{record.get('summary') or '无'}\n\n"
            "只输出 JSON："
            '{"suggested_status":"verified|suspicious|quarantined",'
            '"official_evidence_found":true/false,'
            '"official_url":"确认用官方URL或null",'
            '"artifact_url":"官方PDF/HTML原文URL或null",'
            '"evidence_summary":"一句话依据",'
            '"gaps":["仍缺什么"],'
            '"confidence":0.0}'
        )

    @staticmethod
    def _extract_text(data: Dict[str, Any]) -> str:
        parts = []
        for item in data.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("output_text")
                    if text:
                        parts.append(str(text))
        if data.get("output_text"):
            parts.append(str(data["output_text"]))
        return "\n".join(parts)

    @staticmethod
    def _extract_actions(data: Dict[str, Any]) -> list[dict[str, Any]]:
        actions = []
        for item in data.get("output") or []:
            if isinstance(item, dict) and item.get("type") == "web_search_call":
                action = item.get("action")
                if isinstance(action, dict):
                    actions.append(action)
        return actions


_SERVICE: Optional[AuthenticityReviewService] = None


def get_authenticity_review_service() -> AuthenticityReviewService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = AuthenticityReviewService()
    return _SERVICE
