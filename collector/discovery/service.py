from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from collector.parsers.compliance_parser import extract_json_from_text
from collector.providers.channel_repository import _normalize_openai_base_url
from collector.providers.channel_router import ChannelRouter, get_channel_router
from config.settings import get_settings
from database.connection import get_connection, get_cursor
from database.repository import SourceArtifactRepository, SourceRecordRepository

logger = logging.getLogger(__name__)
DISCOVERY_RECENCY_DAYS = 7


@dataclass(frozen=True)
class DiscoveryTarget:
    country_code: str
    country_name: str
    priority: str
    official_domains: list[str] = field(default_factory=list)
    region: Optional[str] = None
    country_name_en: Optional[str] = None


@dataclass(frozen=True)
class DiscoveryQuery:
    target: DiscoveryTarget
    query: str
    language: str = "en"
    topic: str = "product_cybersecurity_compliance"


@dataclass(frozen=True)
class DiscoveryCandidate:
    title: str
    detail_url: str
    entry_type: str = "regulation"
    artifact_url: Optional[str] = None
    published_date: Optional[str] = None
    summary: Optional[str] = None
    issuing_body: Optional[str] = None
    ai_reason: Optional[str] = None
    official_evidence_reason: Optional[str] = None
    cyber_product_relevance_reason: Optional[str] = None
    ai_confidence: Optional[float] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str
    official_evidence_reason: str = ""
    cyber_product_relevance_reason: str = ""


class DiscoveryTargetRepository:
    """Read enabled countries and their official-domain hints."""

    def list_targets(
        self,
        priorities: Optional[list[str]] = None,
        limit_countries: int = 40,
    ) -> list[DiscoveryTarget]:
        normalized = _normalize_country_priorities(priorities)
        params: list[Any] = []
        where = "WHERE c.enabled = TRUE"
        if normalized:
            where += " AND c.priority::text = ANY(%s)"
            params.append(normalized)
        params.append(limit_countries)
        with get_cursor() as cur:
            cur.execute(
                f"""
                SELECT c.code AS country_code,
                       c.name_zh AS country_name,
                       c.name_en AS country_name_en,
                       c.region,
                       c.priority::TEXT AS priority,
                       COALESCE(array_remove(array_agg(DISTINCT domain.value), NULL), ARRAY[]::TEXT[]) AS official_domains
                FROM countries c
                LEFT JOIN official_sources os
                  ON os.country_code = c.code
                 AND os.enabled = TRUE
                LEFT JOIN LATERAL unnest(os.allowed_domains) AS domain(value)
                  ON TRUE
                {where}
                GROUP BY c.code, c.name_zh, c.name_en, c.region, c.priority
                ORDER BY
                    CASE c.priority::TEXT WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
                    c.code
                LIMIT %s
                """,
                params,
            )
            rows = [dict(row) for row in cur.fetchall()]
        return [
            DiscoveryTarget(
                country_code=row["country_code"],
                country_name=row["country_name"],
                country_name_en=row.get("country_name_en"),
                region=row.get("region"),
                priority=row.get("priority") or "P3",
                official_domains=list(row.get("official_domains") or []),
            )
            for row in rows
        ]


class AIDiscoveryRunRepository:
    def start_run(self, scope: dict[str, Any], countries_count: int, queries_count: int) -> str:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ai_discovery_runs (scope, countries_count, queries_count, status)
                    VALUES (%s::jsonb, %s, %s, 'running')
                    RETURNING id
                    """,
                    (json.dumps(scope, ensure_ascii=False), countries_count, queries_count),
                )
                return str(cur.fetchone()[0])

    def finish_run(
        self,
        run_id: str,
        *,
        candidate_count: int,
        accepted_count: int,
        rejected_count: int,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ai_discovery_runs
                    SET finished_at = NOW(),
                        candidate_count = %s,
                        accepted_count = %s,
                        rejected_count = %s,
                        status = %s,
                        error = %s
                    WHERE id = %s
                    """,
                    (
                        candidate_count,
                        accepted_count,
                        rejected_count,
                        status,
                        (error or "")[:2000] or None,
                        run_id,
                    ),
                )

    def list_runs(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id::TEXT AS id,
                       started_at,
                       finished_at,
                       scope,
                       countries_count,
                       queries_count,
                       candidate_count,
                       accepted_count,
                       rejected_count,
                       status,
                       error
                FROM ai_discovery_runs
                ORDER BY started_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return [dict(row) for row in cur.fetchall()]

    def latest_summary(self, lookback_hours: int = 24) -> dict[str, int]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(candidate_count), 0)::INT AS candidate_count,
                       COALESCE(SUM(accepted_count), 0)::INT AS accepted_count,
                       COALESCE(SUM(rejected_count), 0)::INT AS rejected_count,
                       COUNT(*) FILTER (WHERE status = 'failed')::INT AS failed_run_count
                FROM ai_discovery_runs
                WHERE started_at >= NOW() - (%s * INTERVAL '1 hour')
                """,
                (lookback_hours,),
            )
            run_stats = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT status AS latest_status,
                       started_at AS latest_started_at,
                       finished_at AS latest_finished_at,
                       error AS latest_error
                FROM ai_discovery_runs
                WHERE started_at >= NOW() - (%s * INTERVAL '1 hour')
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (lookback_hours,),
            )
            latest_run = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT COUNT(*) FILTER (
                           WHERE sa.id IS NULL OR COALESCE(sa.download_status, 'pending') = 'pending'
                       )::INT AS artifact_pending_count,
                       COUNT(*) FILTER (WHERE sa.download_status = 'downloaded')::INT AS artifact_downloaded_count,
                       COUNT(*) FILTER (WHERE sa.download_status = 'failed')::INT AS artifact_failed_count
                FROM source_records sr
                LEFT JOIN source_artifacts sa ON sa.source_record_id = sr.id
                WHERE sr.discovery_method = 'ai_weekly_discovery'
                  AND sr.created_at >= NOW() - (%s * INTERVAL '1 hour')
                """,
                (lookback_hours,),
            )
            artifact_stats = dict(cur.fetchone() or {})
        return {**run_stats, **latest_run, **artifact_stats}


class DiscoveryCandidateRepository:
    def list_candidates(
        self,
        limit: int = 50,
        offset: int = 0,
        country_code: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = "WHERE sr.discovery_method = 'ai_weekly_discovery'"
        if country_code:
            where += " AND sr.country_code = %s"
            params.append(country_code.upper())
        params.extend([limit, offset])
        with get_cursor() as cur:
            cur.execute(
                f"""
                SELECT sr.id::TEXT AS id,
                       sr.country_code,
                       c.name_zh AS country_name,
                       sr.title,
                       sr.entry_type,
                       sr.source_url,
                       sr.artifact_url,
                       sr.source_status,
                       sr.discovery_method,
                       sr.source_payload,
                       sr.created_at,
                       sr.updated_at,
                       sa.download_status,
                       sa.download_error
                FROM source_records sr
                LEFT JOIN countries c ON c.code = sr.country_code
                LEFT JOIN source_artifacts sa ON sa.source_record_id = sr.id
                {where}
                ORDER BY sr.created_at DESC
                LIMIT %s OFFSET %s
                """,
                params,
            )
            return [dict(row) for row in cur.fetchall()]


class DiscoveryPlanner:
    def __init__(
        self,
        target_repository: Optional[DiscoveryTargetRepository] = None,
        queries_per_country: int = 3,
    ):
        self._targets = target_repository or DiscoveryTargetRepository()
        self._queries_per_country = queries_per_country

    def build_plan(
        self,
        priorities: Optional[list[str]] = None,
        limit_countries: int = 40,
        queries_per_country: Optional[int] = None,
    ) -> list[DiscoveryQuery]:
        targets = self._targets.list_targets(priorities=priorities, limit_countries=limit_countries)
        per_country = queries_per_country or self._queries_per_country
        today, since = _discovery_date_window()
        recency_hint = f"updated after {since.isoformat()} published after {since.isoformat()} current date {today.isoformat()}"
        queries: list[DiscoveryQuery] = []
        for target in targets:
            name = target.country_name_en or target.country_name or target.country_code
            templates = [
                f'{name} cybersecurity product certification security label IoT official {recency_hint}',
                f'{name} connected product cybersecurity regulation vulnerability reporting official gazette {recency_hint}',
                f'{name} network equipment cybersecurity requirements common criteria certification official {recency_hint}',
                f'{name} logiciel produit connecté cybersécurité certification officiel {recency_hint}',
                f'{name} certificación ciberseguridad producto IoT oficial gobierno {recency_hint}',
                f'{name} certificação cibersegurança produto conectado oficial {recency_hint}',
                f'{name} الأمن السيبراني المنتجات المتصلة شهادة رسمية {recency_hint}',
            ]
            for template in templates[: max(1, per_country)]:
                queries.append(DiscoveryQuery(target=target, query=template))
        return queries


class AIDiscoverySearcher:
    def __init__(self, router: Optional[ChannelRouter] = None):
        self._router = router or get_channel_router()

    def search(self, query: DiscoveryQuery) -> list[DiscoveryCandidate]:
        prompt = _build_ai_discovery_prompt(query)
        response = self._router.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是受控的官方证据发现器，只能返回结构化候选链接。"
                        "不要做真实性结论，不要把候选写成已验证事实。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=3000,
            enable_web_search=True,
        )
        payload = json.loads(extract_json_from_text(response.content))
        if isinstance(payload, dict):
            payload = payload.get("items") or payload.get("candidates") or [payload]
        if not isinstance(payload, list):
            return []
        return [_normalize_candidate_item(item) for item in payload if isinstance(item, dict)]

    def _normalize(self, item: dict[str, Any]) -> DiscoveryCandidate:
        return _normalize_candidate_item(item)


class ResponsesWebSearchDiscoverySearcher:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = "gpt-5.4-mini",
        timeout: int = 90,
        http_client: Optional[httpx.Client] = None,
    ):
        self._api_key = api_key
        self._base_url = _normalize_openai_base_url(base_url).rstrip("/")
        self._model = model
        self._timeout = timeout
        self._http_client = http_client or httpx.Client(timeout=timeout, trust_env=False)

    def search(self, query: DiscoveryQuery) -> list[DiscoveryCandidate]:
        prompt = _build_ai_discovery_prompt(query)
        response = self._http_client.post(
            f"{self._base_url}/responses",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "tools": [{"type": "web_search"}],
                "input": (
                    "你是受控的官方证据发现器。必须使用 web_search 查找官方候选链接，"
                    "只返回 JSON 数组，不做 verified 结论。\n\n"
                    f"{prompt}"
                ),
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        actions = _extract_web_search_actions(data)
        text = _extract_responses_text(data)
        payload = json.loads(extract_json_from_text(text))
        if isinstance(payload, dict):
            payload = payload.get("items") or payload.get("candidates") or [payload]
        if not isinstance(payload, list):
            return []
        candidates: list[DiscoveryCandidate] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            raw_payload = {
                **item,
                "web_search_backend": "responses_web_search",
                "web_search_model": self._model,
                "web_search_actions": actions,
                "responses_id": data.get("id"),
                "responses_usage": data.get("usage"),
            }
            candidates.append(_normalize_candidate_item(raw_payload))
        return candidates


class FallbackDiscoverySearcher:
    def __init__(self, primary: Any, fallback: Any):
        self._primary = primary
        self._fallback = fallback

    def search(self, query: DiscoveryQuery) -> list[DiscoveryCandidate]:
        try:
            return self._primary.search(query)
        except Exception as exc:
            logger.warning("Responses web_search Discovery 失败，回退旧通道 [%s]: %s", query.query, exc)
            return self._fallback.search(query)


class EvidenceValidator:
    def validate(
        self,
        target: DiscoveryTarget,
        query: DiscoveryQuery,
        candidate: DiscoveryCandidate,
    ) -> ValidationResult:
        if not candidate.title or not candidate.detail_url:
            return ValidationResult(False, "候选缺少标题或官方正文链接")

        detail_domain = _domain(candidate.detail_url)
        artifact_domain = _domain(candidate.artifact_url) if candidate.artifact_url else None
        if not detail_domain:
            return ValidationResult(False, "候选 URL 无法解析")
        if detail_domain in UNOFFICIAL_DOMAINS or _has_unofficial_suffix(detail_domain):
            return ValidationResult(False, f"非官方域名: {detail_domain}")
        if artifact_domain and (artifact_domain in UNOFFICIAL_DOMAINS or _has_unofficial_suffix(artifact_domain)):
            return ValidationResult(False, f"非官方工件域名: {artifact_domain}")

        official_ok = _is_official_domain(detail_domain, target.official_domains)
        if artifact_domain:
            official_ok = official_ok and _is_official_domain(artifact_domain, target.official_domains)
        if not official_ok:
            return ValidationResult(False, f"非官方域名: {detail_domain}")

        source_text = " ".join(
            str(value or "")
            for value in (
                candidate.title,
                candidate.detail_url,
                candidate.artifact_url,
                candidate.summary,
                candidate.ai_reason,
                candidate.cyber_product_relevance_reason,
            )
        )
        if is_vulnerability_advisory_not_compliance(source_text):
            return ValidationResult(False, "漏洞/CVE/安全通告，不属于法规/认证/标准候选")
        if _is_generic_product_certification_without_cyber(source_text):
            return ValidationResult(False, "通用产品认证汇总，未体现网络安全产品要求")
        if NOISE_RE.search(source_text) and not STRONG_KNOWN_RE.search(source_text):
            return ValidationResult(False, "非网络安全产品合规主题")
        if _is_news_or_activity_without_formal_source(source_text):
            return ValidationResult(False, "官方新闻/案例页面，不是法规/认证/标准原文")
        if not _is_product_cybersecurity_topic(source_text):
            return ValidationResult(False, "非网络安全产品合规主题")

        official_reason = (
            candidate.official_evidence_reason
            or f"候选链接位于官方/监管/标准机构域名 {detail_domain}"
        )
        product_reason = (
            candidate.cyber_product_relevance_reason
            or "标题/摘要包含网络安全产品、联网产品、认证、标签、漏洞报告或市场准入相关信号"
        )
        return ValidationResult(
            True,
            "accepted",
            official_evidence_reason=official_reason,
            cyber_product_relevance_reason=product_reason,
        )


class CandidateWriter:
    def __init__(
        self,
        source_record_repository=SourceRecordRepository,
        source_artifact_repository=SourceArtifactRepository,
    ):
        self._source_records = source_record_repository
        self._source_artifacts = source_artifact_repository

    def write(
        self,
        target: DiscoveryTarget,
        query: DiscoveryQuery,
        candidate: DiscoveryCandidate,
        validation: ValidationResult,
    ) -> str:
        validation_stage = {
            "mode": "system",
            "status": "pending",
            "reason": "awaiting_ai_or_manual_validation",
            "validated_at": None,
            "validated_by": None,
            "reasons": [],
            "evidence_note": None,
        }
        source_payload = {
            "query": query.query,
            "ai_reason": candidate.ai_reason,
            "official_evidence_reason": validation.official_evidence_reason or candidate.official_evidence_reason,
            "cyber_product_relevance_reason": validation.cyber_product_relevance_reason or candidate.cyber_product_relevance_reason,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "ai_confidence": candidate.ai_confidence,
            "validation_reason": validation.reason,
            "validation_stage": validation_stage,
            "raw_candidate": candidate.raw_payload,
        }
        source_record_id = self._source_records.upsert_candidate(
            country_code=target.country_code,
            title=candidate.title,
            entry_type=_normalize_entry_type(candidate.entry_type),
            source_url=candidate.detail_url,
            artifact_url=candidate.artifact_url or candidate.detail_url,
            published_date=_normalize_date(candidate.published_date),
            official_source_id=None,
            compliance_id=None,
            discovery_method="ai_weekly_discovery",
            source_payload=source_payload,
            source_status="validation_pending",
        )
        return source_record_id

    def write_reference(
        self,
        target: DiscoveryTarget,
        query: DiscoveryQuery,
        candidate: DiscoveryCandidate,
        validation: ValidationResult,
    ) -> str:
        source_payload = {
            "query": query.query,
            "ai_reason": candidate.ai_reason,
            "official_evidence_reason": validation.official_evidence_reason or candidate.official_evidence_reason,
            "cyber_product_relevance_reason": validation.cyber_product_relevance_reason or candidate.cyber_product_relevance_reason,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "ai_confidence": candidate.ai_confidence,
            "reference_kind": "official_dynamic",
            "validation_reason": validation.reason,
            "validation_stage": {
                "mode": "system",
                "status": "reference",
                "reason": "official_dynamic_reference_only",
                "validated_at": datetime.now(timezone.utc).isoformat(),
                "validated_by": "system:evidence_validator",
                "reasons": ["official_news_or_case_page_not_formal_source"],
                "evidence_note": "官方新闻/案例/动态页面，仅作日常通报参考，不进入法规/认证候选、RAG 或规格库。",
            },
            "raw_candidate": candidate.raw_payload,
        }
        return self._source_records.upsert_candidate(
            country_code=target.country_code,
            title=candidate.title,
            entry_type=_normalize_entry_type(candidate.entry_type),
            source_url=candidate.detail_url,
            artifact_url=candidate.artifact_url or candidate.detail_url,
            published_date=_normalize_date(candidate.published_date),
            official_source_id=None,
            compliance_id=None,
            discovery_method="ai_weekly_discovery",
            source_payload=source_payload,
            source_status="reference",
        )


class CandidateValidationService:
    """AI Discovery 候选校验层。

    这里的 accepted 只代表可以进入 artifact 下载/审核队列，不代表 verified。
    """

    VALID_MODES = {"manual", "ai"}
    VALID_DECISIONS = {"accepted", "rejected", "needs_manual"}

    def __init__(
        self,
        router: Optional[ChannelRouter] = None,
        source_record_repository=SourceRecordRepository,
        source_artifact_repository=SourceArtifactRepository,
    ):
        self._router = router or get_channel_router()
        self._source_records = source_record_repository
        self._source_artifacts = source_artifact_repository

    def validate(
        self,
        source_record_id: str,
        *,
        mode: str,
        decision: Optional[str] = None,
        reasons: Optional[list[str]] = None,
        evidence_note: Optional[str] = None,
        checked_by: str = "system",
    ) -> dict[str, Any]:
        if mode not in self.VALID_MODES:
            raise ValueError("mode 必须是 manual 或 ai")
        record = self._source_records.get_by_id(source_record_id)
        if not record:
            raise ValueError("source_record 不存在")

        if mode == "ai":
            ai_decision = self._ai_decide(record)
            decision = ai_decision["decision"]
            reasons = ai_decision["reasons"]
            evidence_note = ai_decision["evidence_note"]
        else:
            if decision not in self.VALID_DECISIONS:
                raise ValueError("decision 必须是 accepted/rejected/needs_manual")
            if not reasons:
                raise ValueError("reasons 不能为空")
            if not (evidence_note or "").strip():
                raise ValueError("evidence_note 不能为空")

        assert decision is not None
        validation_stage = {
            "mode": mode,
            "status": decision,
            "reasons": reasons or [],
            "evidence_note": evidence_note,
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "validated_by": checked_by,
        }
        source_status = self._source_status_for_decision(decision)
        if not self._source_records.update_validation(
            source_record_id,
            source_status=source_status,
            validation_stage=validation_stage,
        ):
            raise ValueError("source_record 更新失败")

        artifact_id = None
        if decision == "accepted":
            artifact_id = self._ensure_pending_artifact(record)

        return {
            "source_record_id": source_record_id,
            "source_status": source_status,
            "validation_stage": validation_stage,
            "source_artifact_id": artifact_id,
        }

    def _ai_decide(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = record.get("source_payload") or {}
        relevance_text = _record_candidate_relevance_text(record)
        if is_vulnerability_advisory_not_compliance(relevance_text):
            return {
                "decision": "rejected",
                "reasons": ["vulnerability_advisory_not_compliance"],
                "evidence_note": "该候选是 CVE/漏洞通告、厂商产品漏洞修复公告或漏洞提交入口，不属于网络安全产品合规法规、认证、标准或市场准入要求。",
            }
        if _is_generic_product_certification_without_cyber(relevance_text):
            return {
                "decision": "rejected",
                "reasons": ["generic_product_certification_not_cybersecurity"],
                "evidence_note": "该候选属于通用产品认证/CCC实施规则汇总，未体现网络安全产品、联网产品安全或网络设备安全要求，不进入网安合规候选。",
            }
        if not _is_product_cybersecurity_topic(relevance_text):
            return {
                "decision": "rejected",
                "reasons": ["not_cyber_product_compliance"],
                "evidence_note": "候选自身标题、链接和摘要未体现网络安全产品合规要求；搜索词中的网安关键词不能作为入库依据。",
            }
        prompt = (
            "你是网安合规官方源候选的二次校验助手。"
            "只能基于候选记录本身判断是否值得进入下载/人工审核队列；"
            "不得判定 verified，不得编造外部事实。"
            "若候选只是通用产品认证、CCC目录、普通质量/电气/电磁/电信准入，且没有明确网络安全产品要求，必须输出 rejected。"
            "若候选是 CVE、漏洞安全通告、CERT/CSIRT advisory、具体厂商/产品漏洞修复公告、漏洞提交表单或 VDP 入口，也必须输出 rejected。"
            "若官方性或产品网络安全相关性不清楚，输出 needs_manual。\n\n"
            f"国家：{record.get('country_code')}\n"
            f"标题：{record.get('title')}\n"
            f"类型：{record.get('entry_type')}\n"
            f"source_url：{record.get('source_url')}\n"
            f"artifact_url：{record.get('artifact_url')}\n"
            f"搜索词：{payload.get('query')}\n"
            f"AI发现理由：{payload.get('ai_reason')}\n"
            f"官方性理由：{payload.get('official_evidence_reason')}\n"
            f"产品网安相关性理由：{payload.get('cyber_product_relevance_reason')}\n\n"
            "输出 JSON："
            '{"decision":"accepted|rejected|needs_manual",'
            '"reasons":["简短原因"],'
            '"evidence_note":"一句话校验备注"}'
        )
        try:
            response = self._router.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=600,
                enable_web_search=False,
            )
            data = json.loads(extract_json_from_text(response.content))
            decision = str(data.get("decision") or "needs_manual")
            if decision not in self.VALID_DECISIONS:
                decision = "needs_manual"
            reasons = data.get("reasons") if isinstance(data.get("reasons"), list) else []
            evidence_note = str(data.get("evidence_note") or "").strip()
        except Exception:
            decision = "needs_manual"
            reasons = ["ai_validation_failed"]
            evidence_note = "AI 校验失败，保留给人工复核。"
        return {
            "decision": decision,
            "reasons": [str(item) for item in reasons if str(item).strip()] or ["ai_validation_reviewed"],
            "evidence_note": evidence_note or "AI 已完成候选校验，但未给出充分备注。",
        }

    def _ensure_pending_artifact(self, record: dict[str, Any]) -> Optional[str]:
        get_existing = getattr(self._source_artifacts, "get_by_source_record_id", None)
        if callable(get_existing):
            existing = get_existing(str(record["id"]))
            if existing:
                return str(existing["id"])
        return self._source_artifacts.upsert_for_compliance(
            compliance_id=None,
            official_url=record.get("source_url"),
            artifact_url=record.get("artifact_url") or record.get("source_url"),
            artifact_type=None,
            artifact_sha256=None,
            download_status="pending",
            download_error=None,
            source_record_id=str(record["id"]),
        )

    @staticmethod
    def _source_status_for_decision(decision: str) -> str:
        if decision == "accepted":
            return "candidate"
        if decision == "rejected":
            return "rejected"
        return "validation_pending"


class AIDiscoveryService:
    def __init__(
        self,
        planner: Optional[DiscoveryPlanner] = None,
        searcher: Optional[AIDiscoverySearcher] = None,
        validator: Optional[EvidenceValidator] = None,
        writer: Optional[CandidateWriter] = None,
        run_repository: Optional[AIDiscoveryRunRepository] = None,
        candidate_validation_service: Optional[CandidateValidationService] = None,
    ):
        self._planner = planner or DiscoveryPlanner()
        self._searcher = searcher or AIDiscoverySearcher()
        self._validator = validator or EvidenceValidator()
        self._writer = writer or CandidateWriter()
        self._runs = run_repository or AIDiscoveryRunRepository()
        self._candidate_validation = candidate_validation_service or CandidateValidationService()

    def run(
        self,
        priorities: Optional[list[str]] = None,
        limit_countries: int = 40,
        queries_per_country: int = 3,
        validation_mode: str = "ai",
    ) -> dict[str, Any]:
        if validation_mode not in {"ai", "manual"}:
            raise ValueError("validation_mode 必须是 ai 或 manual")
        plan = self._planner.build_plan(
            priorities=priorities,
            limit_countries=limit_countries,
            queries_per_country=queries_per_country,
        )
        countries_count = len({query.target.country_code for query in plan})
        scope = {
            "priorities": priorities or ["P1"],
            "limit_countries": limit_countries,
            "queries_per_country": queries_per_country,
            "validation_mode": validation_mode,
        }
        run_id = self._runs.start_run(scope=scope, countries_count=countries_count, queries_count=len(plan))
        candidate_count = 0
        accepted_count = 0
        rejected_count = 0
        reference_count = 0
        errors: list[str] = []

        for query in plan:
            try:
                candidates = self._searcher.search(query)
            except Exception as exc:
                errors.append(f"{query.target.country_code} · {query.query}: {exc}")
                logger.warning("AI Discovery 查询失败 [%s]: %s", query.query, exc)
                continue

            for candidate in candidates:
                candidate_count += 1
                validation = self._validator.validate(query.target, query, candidate)
                if not validation.accepted:
                    if _is_reference_only_validation(validation):
                        try:
                            self._writer.write_reference(query.target, query, candidate, validation)
                            reference_count += 1
                        except Exception as exc:
                            rejected_count += 1
                            errors.append(f"{candidate.title}: 官方动态参考写入失败: {exc}")
                            logger.warning("AI Discovery 官方动态参考写入失败 [%s]: %s", candidate.title, exc)
                    else:
                        rejected_count += 1
                    continue
                try:
                    source_record_id = self._writer.write(query.target, query, candidate, validation)
                    accepted_count += 1
                    if validation_mode == "ai":
                        try:
                            self._candidate_validation.validate(
                                source_record_id,
                                mode="ai",
                                checked_by="ai_discovery",
                            )
                        except Exception as exc:
                            errors.append(f"{candidate.title}: AI 校验失败: {exc}")
                            logger.warning("AI Discovery 候选 AI 校验失败 [%s]: %s", candidate.title, exc)
                except Exception as exc:
                    rejected_count += 1
                    errors.append(f"{candidate.title}: {exc}")
                    logger.warning("AI Discovery 候选写入失败 [%s]: %s", candidate.title, exc)

        status = "success"
        if errors and candidate_count == 0 and accepted_count == 0:
            status = "failed"
        elif errors:
            status = "success_with_errors"
        error = "\n".join(errors)[:2000] if errors else None
        self._runs.finish_run(
            run_id,
            candidate_count=candidate_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            status=status,
            error=error,
        )
        return {
            "run_id": run_id,
            "countries_count": countries_count,
            "queries_count": len(plan),
            "candidate_count": candidate_count,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "reference_count": reference_count,
            "status": status,
            "error": error,
        }


def get_ai_discovery_service() -> AIDiscoveryService:
    return AIDiscoveryService(searcher=build_discovery_searcher())


def build_discovery_searcher() -> Any:
    settings = get_settings()
    discovery = settings.discovery
    if (
        discovery.search_backend == "responses_web_search"
        and settings.uniapi.api_key
        and settings.uniapi.base_url
    ):
        return FallbackDiscoverySearcher(
            primary=ResponsesWebSearchDiscoverySearcher(
                api_key=settings.uniapi.api_key,
                base_url=settings.uniapi.base_url,
                model=discovery.web_search_model or "gpt-5.4-mini",
                timeout=discovery.web_search_timeout,
            ),
            fallback=AIDiscoverySearcher(),
        )
    return AIDiscoverySearcher()


def get_ai_discovery_run_repository() -> AIDiscoveryRunRepository:
    return AIDiscoveryRunRepository()


def get_ai_discovery_candidate_repository() -> DiscoveryCandidateRepository:
    return DiscoveryCandidateRepository()


UNOFFICIAL_DOMAINS = {
    "wikipedia.org",
    "wikimedia.org",
    "example.com",
    "medium.com",
    "github.com",
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "lexology.com",
    "mondaq.com",
    "dlapiper.com",
    "whitecase.com",
    "twobirds.com",
    "globalcompliancenews.com",
    "complianceandrisks.com",
}

OFFICIAL_DOMAIN_SUFFIXES = (
    ".gov",
    ".gov.",
    ".gob.",
    ".gouv.",
    ".go.",
    ".gc.ca",
    ".europa.eu",
    ".int",
)

OFFICIAL_EXACT_OR_SUFFIX = {
    "eur-lex.europa.eu",
    "digital-strategy.ec.europa.eu",
    "enisa.europa.eu",
    "nist.gov",
    "csrc.nist.gov",
    "nvlpubs.nist.gov",
    "fcc.gov",
    "docs.fcc.gov",
    "legislation.gov.uk",
    "ncsc.gov.uk",
    "iso.org",
    "iec.ch",
    "etsi.org",
    "commoncriteriaportal.org",
    "csa.gov.sg",
    "cyber.gouv.fr",
    "legifrance.gouv.fr",
}

NOISE_RE = re.compile(
    r"(electromagnetic|emc|radio frequency|spectrum|broadcast|telecom licence|"
    r"type approval|homologation|electrical safety|energy efficiency|rohs|weee|quarterly statistics|"
    r"电磁|射频|频谱|广播|电气安全|能效|环保)",
    re.IGNORECASE,
)

CYBER_SIGNAL_RE = re.compile(
    r"(cyber|cybersecurity|network security|information security|security requirements|"
    r"vulnerability|incident reporting|secure by design|product security|"
    r"网络安全|信息安全|漏洞|安全更新|安全要求|安全认证)",
    re.IGNORECASE,
)

PRODUCT_SIGNAL_RE = re.compile(
    r"(product|device|equipment|iot|internet of things|connected product|connectable product|"
    r"software|router|switch|firewall|gateway|wireless|certification|scheme|label|trust mark|"
    r"common criteria|security label|market access|conformity|"
    r"产品|设备|联网产品|物联网|软件|路由器|交换机|防火墙|网关|无线|认证|标签|标识|市场准入)",
    re.IGNORECASE,
)

STRONG_KNOWN_RE = re.compile(
    r"(cyber resilience act|cyber trust mark|cybersecurity labelling scheme|jc-star|jc star|"
    r"common criteria|eucc|psti|product security and telecommunications infrastructure|"
    r"network product security|secure connected products)",
    re.IGNORECASE,
)

NEWS_OR_ACTIVITY_RE = re.compile(
    r"(news|press release|news and press|gallery|receive(?:s|d)?|awarded|launch(?:es|ed)?|"
    r"announc(?:e|es|ed|ement)|statistics|case stud(?:y|ies)|systems for|"
    r"新闻|动态|报道|案例|活动|获(?:得|颁)|颁发|发布会|统计)",
    re.IGNORECASE,
)

GENERIC_PRODUCT_CERTIFICATION_RE = re.compile(
    r"(强制性产品认证实施规则汇总|强制性产品认证目录|ccc\s*(?:implementation|certification|rules?)|"
    r"compulsory product certification|mandatory product certification|"
    r"product certification implementation rules|qzxcprz|普通产品认证|质量认证)",
    re.IGNORECASE,
)

VULNERABILITY_ADVISORY_RE = re.compile(
    r"(\bcve-\d{4}-\d{4,}\b|\bcve\b|"
    r"security advisory|cert[- ]?in advisory|advisories|advisory|"
    r"alertas?-de-seguridad|alert[ae]s? de seguridad|alert(?:s)? and bulletin|"
    r"bollettin[io]|bulletin|bolet[ií]n|"
    r"critical vulnerability|vulnerabilit(?:y|ies)|vulnerabilidad|vulnerabilit[àa]|"
    r"remote code execution|\brce\b|authentication bypass|bypass crítico|"
    r"active exploitation|exploited vulnerability|zero[- ]day|patch(?:ed|ing)?|"
    r"report vulnerability|vulnerability submission|vulnerability disclosure|"
    r"漏洞通告|安全通告|漏洞预警|漏洞公告|漏洞提交|漏洞报告入口|远程代码执行|认证绕过|补丁修复)",
    re.IGNORECASE,
)

OPERATIONAL_VULNERABILITY_ADVISORY_RE = re.compile(
    r"(\bcve-\d{4}-\d{4,}\b|\bcve\b|"
    r"/advisories?|/alertas?-de-seguridad|/alerts?|/bulletins?|"
    r"security advisories|security advisory|cert[- ]?in advisory|critical vulnerability|"
    r"vulnerabilidad crítica|alerta cib(?:e|é)rn(?:e|é)tica|alerta de vulnerabilidade|risolte vulnerabilit[àa]|"
    r"remote code execution|\brce\b|authentication bypass|bypass crítico|"
    r"active exploitation|exploited vulnerability|zero[- ]day|"
    r"report(?:ar)? vulnerabil|report a vulnerability|vulnerability-report|vulnerability submission|"
    r"漏洞通告|安全通告|漏洞预警|漏洞公告|漏洞提交|漏洞报告入口|远程代码执行|认证绕过|补丁修复)",
    re.IGNORECASE,
)

FORMAL_VULNERABILITY_REQUIREMENT_RE = re.compile(
    r"(vulnerability reporting obligation|coordinated vulnerability disclosure requirement|"
    r"vulnerability handling requirement|essential cybersecurity requirement|"
    r"cyber resilience act|regulation\s*\(|directive\s*\(|law|act|standard|certification scheme|"
    r"法规|条例|法律|法案|标准|认证方案|漏洞报告义务|漏洞处理要求|安全更新要求)",
    re.IGNORECASE,
)

FORMAL_SOURCE_RE = re.compile(
    r"(\b(?:regulation|directive|law|act|decree|order|ordinance|circular|standard|requirement(?:s)?|"
    r"criteria|rule(?:s)?|scheme|certification scheme|label(?:l)?ing scheme|guideline(?:s)?|"
    r"framework|program(?:me)?|measure(?:s)?|implementation rule(?:s)?|official journal|gazette)\b|"
    r"法规|条例|法律|法案|法令|命令|通告|标准|要求|准则|规则|方案|认证方案|认证规则|"
    r"实施规则|实施细则|管理办法|官方公报|公报)",
    re.IGNORECASE,
)


def _is_news_or_activity_without_formal_source(text: str) -> bool:
    return bool(NEWS_OR_ACTIVITY_RE.search(text) and not FORMAL_SOURCE_RE.search(text))


def _is_generic_product_certification_without_cyber(text: str) -> bool:
    if not GENERIC_PRODUCT_CERTIFICATION_RE.search(text):
        return False
    return not bool(STRONG_KNOWN_RE.search(text) or CYBER_SIGNAL_RE.search(text))


def is_vulnerability_advisory_not_compliance(text: str) -> bool:
    if not VULNERABILITY_ADVISORY_RE.search(text):
        return False
    if STRONG_KNOWN_RE.search(text):
        return False
    if not OPERATIONAL_VULNERABILITY_ADVISORY_RE.search(text):
        return False
    # Keep formal legal/certification sources that define vulnerability handling
    # obligations; exclude operational CVE/advisory/patch notices and VDP forms.
    if FORMAL_VULNERABILITY_REQUIREMENT_RE.search(text) and not OPERATIONAL_VULNERABILITY_ADVISORY_RE.search(text):
        return False
    return True


def _is_reference_only_validation(validation: ValidationResult) -> bool:
    return "官方新闻/案例页面" in validation.reason


def _normalize_country_priorities(priorities: Optional[list[str]]) -> list[str]:
    if not priorities:
        return ["P1"]
    result: list[str] = []
    for priority in priorities:
        value = str(priority).upper()
        if value == "P0":
            value = "P1"
        if value in {"P1", "P2", "P3"} and value not in result:
            result.append(value)
    return result


def _build_ai_discovery_prompt(query: DiscoveryQuery) -> str:
    target = query.target
    domains = ", ".join(target.official_domains) or "该国政府、监管机构、官方公报、标准机构或官方认证机构域名"
    today, since = _discovery_date_window()
    return f"""请联网搜索并只返回结构化候选链接，用于“网安产品合规官方证据发现”。

国家/地区：{target.country_name} ({target.country_code})
搜索任务：{query.query}
优先官方域名线索：{domains}
当前日期：{today.isoformat()}
搜索时间窗：只查找最近{DISCOVERY_RECENCY_DAYS}天内发布或更新的官方原文/官方项目页，即 {since.isoformat()} 至 {today.isoformat()}。

只收集与网络安全产品合规有关的官方证据：
- 网络安全法规、联网产品/IoT/软件/网络设备安全要求
- 产品网络安全认证、标签、信任标识、Common Criteria、EUCC、PSTI、CRA 类制度
- 法规/认证/标准正文里的漏洞报告义务、安全更新义务、合格评定、市场准入规则

必须排除：
- 新闻、律所解读、博客、供应商页面、Wikipedia、PDF聚合站
- 没有明确发布时间或更新时间依据的内容；如果只能找到旧材料，不要返回旧闻作为“今日变化”
- 官方新闻/案例/统计/获奖报道本身不算候选，除非页面就是认证方案、法规正文、标准正文或实施规则
- CVE、漏洞安全通告、CERT/CSIRT advisory、具体厂商/产品漏洞修复公告、漏洞提交表单、VDP 入口
- 电磁/射频/频谱/普通电信准入/电气安全/环保/能效/ISO 9001/纯管理体系

输出 JSON 数组，最多 5 条：
[
  {{
    "title": "官方标题",
    "title_zh": "官方标题的简体中文翻译，保留法规编号、机构名和英文缩写",
    "detail_url": "官方正文页或官方项目页 URL",
    "artifact_url": "官方 PDF/HTML 工件 URL，没有则 null",
    "entry_type": "regulation|standard|certification",
    "published_date": "YYYY-MM-DD；必须填写官方页面的发布时间或更新时间，published_date 不得为 null",
    "issuing_body": "官方机构名或 null",
    "summary": "为什么是产品网络安全合规候选，一句话",
    "summary_zh": "summary 的简体中文翻译，不能新增事实",
    "ai_reason": "为什么值得进入待审核候选",
    "official_evidence_reason": "为什么判断为官方来源",
    "cyber_product_relevance_reason": "为什么与网络安全产品法规/认证/标准有关",
    "ai_confidence": 0.0
  }}
]

只输出 JSON，不要输出解释。"""


def _discovery_date_window(today: Optional[date] = None) -> tuple[date, date]:
    current = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    return current, current - timedelta(days=DISCOVERY_RECENCY_DAYS)


def _normalize_candidate_item(item: dict[str, Any]) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        title=str(item.get("title") or item.get("name") or "").strip(),
        detail_url=str(item.get("detail_url") or item.get("url") or item.get("official_url") or "").strip(),
        artifact_url=(str(item.get("artifact_url") or item.get("pdf_url") or "").strip() or None),
        entry_type=_normalize_entry_type(item.get("entry_type")),
        published_date=_normalize_date(item.get("published_date") or item.get("date")),
        summary=(str(item.get("summary") or "").strip() or None),
        issuing_body=(str(item.get("issuing_body") or item.get("agency") or "").strip() or None),
        ai_reason=(str(item.get("ai_reason") or item.get("reason") or "").strip() or None),
        official_evidence_reason=(str(item.get("official_evidence_reason") or item.get("why_official") or "").strip() or None),
        cyber_product_relevance_reason=(str(item.get("cyber_product_relevance_reason") or item.get("why_relevant") or "").strip() or None),
        ai_confidence=_normalize_confidence(item.get("ai_confidence") or item.get("confidence")),
        raw_payload=item,
    )


def _extract_web_search_actions(data: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in data.get("output") or []:
        if isinstance(item, dict) and item.get("type") == "web_search_call":
            action = item.get("action")
            if isinstance(action, dict):
                actions.append(action)
    return actions


def _extract_responses_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            text = part.get("text") or part.get("output_text")
            if text:
                parts.append(str(text))
    if data.get("output_text"):
        parts.append(str(data["output_text"]))
    return "\n".join(parts).strip()


def _domain(url: Optional[str]) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _has_unofficial_suffix(domain: str) -> bool:
    return any(domain == bad or domain.endswith("." + bad) for bad in UNOFFICIAL_DOMAINS)


def _is_official_domain(domain: str, allowed_domains: Iterable[str]) -> bool:
    normalized_allowed = [(_domain(item) if item.startswith(("http://", "https://")) else item).lower().lstrip("www.") for item in allowed_domains if item]
    if any(domain == allowed or domain.endswith("." + allowed) for allowed in normalized_allowed):
        return True
    if domain in OFFICIAL_EXACT_OR_SUFFIX or any(domain.endswith("." + item) for item in OFFICIAL_EXACT_OR_SUFFIX):
        return True
    for suffix in OFFICIAL_DOMAIN_SUFFIXES:
        marker = suffix.strip(".")
        if domain == marker or domain.endswith("." + marker) or f".{marker}." in domain:
            return True
    return False


def _is_product_cybersecurity_topic(text: str) -> bool:
    if NOISE_RE.search(text) and not STRONG_KNOWN_RE.search(text):
        return False
    if STRONG_KNOWN_RE.search(text):
        return True
    return bool(CYBER_SIGNAL_RE.search(text) and PRODUCT_SIGNAL_RE.search(text))


def _record_candidate_relevance_text(record: dict[str, Any]) -> str:
    payload = record.get("source_payload") or {}
    raw = payload.get("raw_candidate") if isinstance(payload.get("raw_candidate"), dict) else {}
    return " ".join(
        str(value or "")
        for value in (
            record.get("title"),
            record.get("source_url"),
            record.get("artifact_url"),
            raw.get("title"),
            raw.get("title_zh"),
            raw.get("summary"),
            raw.get("summary_zh"),
            payload.get("ai_reason"),
            payload.get("official_evidence_reason"),
            payload.get("cyber_product_relevance_reason"),
        )
    )


def _normalize_entry_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"regulation", "standard", "certification"}:
        return text
    if text in {"scheme", "label", "certificate"}:
        return "certification"
    if text in {"law", "act", "rule", "decree"}:
        return "regulation"
    return "regulation"


def _normalize_date(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if not match:
        return None
    candidate = match.group(0)
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


def _normalize_confidence(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1:
        number = number / 100.0
    return max(0.0, min(1.0, number))
