"""
database/repository.py
数据访问层 - 封装所有对合规知识库的 CRUD 操作
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import psycopg2.extras

from database.connection import get_connection, get_cursor

logger = logging.getLogger(__name__)

VERIFIED_STATUS = "verified"
REVIEW_REQUIRED_REASONS = ["requires_review_before_verified"]
PRODUCT_REGIME_CATEGORY = "product_regime"
GENERAL_CYBER_LAW_CATEGORY = "general_cyber_law"
CRA_LIFECYCLE_MILESTONES = [
    {
        "milestone_key": "entry_into_force",
        "milestone_type": "entry_into_force",
        "milestone_label_zh": "法规已生效 / entered into force",
        "milestone_label_en": "Entered into force",
        "milestone_date": date(2024, 12, 10),
        "obligation_scope": "Regulation (EU) 2024/2847 became EU law.",
        "legal_basis": "Article 71(1)",
        "source_note": "EUR-Lex official text: Regulation (EU) 2024/2847, Article 71.",
        "alertable": False,
        "priority": 10,
    },
    {
        "milestone_key": "notified_body_rules_apply",
        "milestone_type": "application",
        "milestone_label_zh": "合格评定机构通知规则开始适用",
        "milestone_label_en": "Rules on notification of conformity assessment bodies apply",
        "milestone_date": date(2026, 6, 11),
        "obligation_scope": "Chapter IV (Articles 35 to 51) on notification of conformity assessment bodies.",
        "legal_basis": "Article 71(2); Chapter IV (Articles 35 to 51)",
        "source_note": "EUR-Lex official text: Regulation (EU) 2024/2847, Article 71.",
        "alertable": True,
        "priority": 20,
    },
    {
        "milestone_key": "reporting_obligations_apply",
        "milestone_type": "obligation",
        "milestone_label_zh": "漏洞与严重事件报告义务开始适用",
        "milestone_label_en": "Reporting obligations for actively exploited vulnerabilities and severe incidents apply",
        "milestone_date": date(2026, 9, 11),
        "obligation_scope": "Article 14 reporting obligations for actively exploited vulnerabilities and severe incidents.",
        "legal_basis": "Article 71(2); Article 14",
        "source_note": "EUR-Lex official text: Regulation (EU) 2024/2847, Article 71.",
        "alertable": True,
        "priority": 30,
    },
    {
        "milestone_key": "full_application",
        "milestone_type": "application",
        "milestone_label_zh": "主要义务 / 全面适用",
        "milestone_label_en": "Full application of the main obligations",
        "milestone_date": date(2027, 12, 11),
        "obligation_scope": "The Regulation generally applies from this date.",
        "legal_basis": "Article 71(2)",
        "source_note": "EUR-Lex official text: Regulation (EU) 2024/2847, Article 71.",
        "alertable": True,
        "priority": 40,
    },
]

_PRODUCT_REGIME_RE = re.compile(
    r"("
    r"certification|scheme|label|labeling|trust mark|common criteria|protection profile|"
    r"niap|cspn|cyber essentials|cyber fundamentals|qcvn|jc-star|jc star|"
    r"technical regulation|conformity|approval|product security|secure[- ]by[- ]design|"
    r"cyber resilience act|products with digital elements|horizontal cybersecurity requirements|"
    r"iot|internet of things|connectable product|network equipment|network device|"
    r"router|switch|firewall|gateway|wireless ap|cryptographic module|crypto module|"
    r"认证|检测|测评|标签|标识|计划|方案|目录|清单|网络关键设备|网络安全专用产品|"
    r"专用网络安全产品|商用密码产品|密码产品|关键信息基础设施产品|联网产品|"
    r"物联网|智能设备|网络设备|路由器|交换机|网关|防火墙|安全产品"
    r")",
    re.IGNORECASE,
)


def classify_regime_category(record: Dict[str, Any]) -> str:
    """Classify a verified record as product regime or general cyber law.

    `applicable_products` is intentionally not enough: many legacy general
    laws were broad-tagged with products and must not become product
    requirements just because the array contains "switch".
    """
    explicit = record.get("regime_category")
    if explicit in {PRODUCT_REGIME_CATEGORY, GENERAL_CYBER_LAW_CATEGORY}:
        return explicit
    if record.get("entry_type") == "certification":
        return PRODUCT_REGIME_CATEGORY
    text = " ".join(
        str(record.get(key) or "")
        for key in (
            "name",
            "scope_description",
            "summary",
            "remarks",
            "regulation_basis",
            "requirements",
            "technical_standards",
            "issuing_body",
        )
    )
    return PRODUCT_REGIME_CATEGORY if _PRODUCT_REGIME_RE.search(text) else GENERAL_CYBER_LAW_CATEGORY


def source_record_not_verified_filter_sql(source_alias: str = "sr") -> str:
    """SQL predicate: candidate source is not already represented by verified index."""
    return f"""
                  AND NOT EXISTS (
                      SELECT 1
                      FROM compliance_index ci_existing
                      WHERE ci_existing.status = 'active'
                        AND ci_existing.authenticity_status = 'verified'
                        AND ci_existing.country_code = {source_alias}.country_code
                        AND (
                            ci_existing.compliance_id = {source_alias}.compliance_id
                            OR
                            ci_existing.official_url IN ({source_alias}.source_url, {source_alias}.artifact_url)
                            OR lower(btrim(ci_existing.name)) = lower(btrim({source_alias}.title))
                            OR (
                                ci_existing.entry_type::text = {source_alias}.entry_type::text
                                AND length(btrim(ci_existing.name)) >= 8
                                AND length(btrim({source_alias}.title)) >= 8
                                AND similarity(ci_existing.name, {source_alias}.title) >= 0.72
                            )
                        )
                  )
    """


def source_record_not_known_filter_sql(source_alias: str = "sr") -> str:
    """SQL predicate for digest/reporting: source is new to the local corpus.

    This is stricter than source_record_not_verified_filter_sql: the morning
    brief should not re-announce records already linked to compliance data or
    previously seen source_records, even if they are not verified yet.
    """
    return f"""
                  AND {source_alias}.compliance_id IS NULL
                  {source_record_not_verified_filter_sql(source_alias)}
                  AND NOT EXISTS (
                      SELECT 1
                      FROM compliance_knowledge ck_existing
                      WHERE ck_existing.status = 'active'
                        AND ck_existing.country_code = {source_alias}.country_code
                        AND (
                            ck_existing.id = {source_alias}.compliance_id
                            OR ck_existing.official_url IN ({source_alias}.source_url, {source_alias}.artifact_url)
                            OR ck_existing.official_url_backup IN ({source_alias}.source_url, {source_alias}.artifact_url)
                            OR lower(btrim(ck_existing.name)) = lower(btrim({source_alias}.title))
                            OR lower(btrim(COALESCE(ck_existing.name_local, ''))) = lower(btrim({source_alias}.title))
                            OR (
                                ck_existing.entry_type::text = {source_alias}.entry_type::text
                                AND length(btrim(ck_existing.name)) >= 8
                                AND length(btrim({source_alias}.title)) >= 8
                                AND similarity(ck_existing.name, {source_alias}.title) >= 0.72
                            )
                        )
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM source_records sr_seen
                      WHERE sr_seen.id <> {source_alias}.id
                        AND sr_seen.country_code = {source_alias}.country_code
                        AND sr_seen.created_at < {source_alias}.created_at
                        AND COALESCE(sr_seen.source_status, '') <> 'rejected'
                        AND (
                            NULLIF(lower(regexp_replace(COALESCE(sr_seen.source_url, ''), '/+$', '')), '') IN (
                                lower(regexp_replace(COALESCE({source_alias}.source_url, ''), '/+$', '')),
                                lower(regexp_replace(COALESCE({source_alias}.artifact_url, ''), '/+$', ''))
                            )
                            OR NULLIF(lower(regexp_replace(COALESCE(sr_seen.artifact_url, ''), '/+$', '')), '') IN (
                                lower(regexp_replace(COALESCE({source_alias}.source_url, ''), '/+$', '')),
                                lower(regexp_replace(COALESCE({source_alias}.artifact_url, ''), '/+$', ''))
                            )
                            OR lower(btrim(sr_seen.title)) = lower(btrim({source_alias}.title))
                            OR (
                                sr_seen.entry_type::text = {source_alias}.entry_type::text
                                AND length(btrim(sr_seen.title)) >= 8
                                AND length(btrim({source_alias}.title)) >= 8
                                AND similarity(sr_seen.title, {source_alias}.title) >= 0.78
                            )
                        )
                  )
    """


def _has_official_url(data: Dict[str, Any]) -> bool:
    official_url = (data.get("official_url") or "").strip()
    return official_url.startswith(("https://", "http://"))


def _has_source_artifact_evidence(data: Dict[str, Any]) -> bool:
    return bool(
        data.get("source_artifact_sha256")
        or data.get("source_document_id")
        or data.get("source_artifact_url")
    )


def _has_evidence_note(data: Dict[str, Any], evidence: Optional[str] = None) -> bool:
    return bool((evidence or data.get("authenticity_evidence") or data.get("evidence_note") or "").strip())


def _ensure_compliance_create_review_gate(data: Dict[str, Any]) -> None:
    """Ensure new formal records cannot enter the trusted pool without evidence."""
    wants_verified = bool(data.get("verified")) or data.get("authenticity_status") == VERIFIED_STATUS
    if wants_verified:
        if not _has_official_url(data) or not _has_source_artifact_evidence(data) or not _has_evidence_note(data):
            raise ValueError("verified 入库必须带官方证据链：official_url + 原文工件/文档 + 证据备注")
        data["verified"] = True
        data["authenticity_status"] = VERIFIED_STATUS
        data.setdefault("authenticity_risk_score", 0)
        return

    data["verified"] = False
    data.setdefault("authenticity_status", "candidate")
    data.setdefault("authenticity_risk_score", 60)
    reasons = data.get("authenticity_reasons")
    if isinstance(reasons, str):
        try:
            reasons = json.loads(reasons)
        except json.JSONDecodeError:
            reasons = [reasons]
    if not isinstance(reasons, list):
        reasons = []
    for reason in REVIEW_REQUIRED_REASONS:
        if reason not in reasons:
            reasons.append(reason)
    data["authenticity_reasons"] = reasons
    data.setdefault(
        "authenticity_evidence",
        "新入库条目默认进入候选池；必须完成官方正文页/PDF工件闭环和真实性审核后才能标记 verified。",
    )


def _ensure_verified_review_gate(
    record: Dict[str, Any],
    authenticity_status: str,
    evidence: Optional[str] = None,
) -> None:
    if authenticity_status != VERIFIED_STATUS:
        return
    if not _has_official_url(record) or not _has_source_artifact_evidence(record):
        raise ValueError("verified 审核必须先完成官方原文工件闭环：official_url + source_artifact/source_document")
    if not _has_evidence_note(record, evidence=evidence):
        raise ValueError("verified 审核必须填写可读证据备注")


# ============================================================
# 合规知识库 Repository
# ============================================================

class ComplianceRepository:
    """compliance_knowledge 表的数据访问层"""

    # ------ 查询 ------

    @staticmethod
    def get_by_id(record_id: str) -> Optional[Dict]:
        """根据 UUID 获取单条记录"""
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM compliance_knowledge WHERE id = %s",
                (record_id,),
            )
            return cur.fetchone()

    @staticmethod
    def list_by_country(
        country_code: str,
        entry_type: Optional[str] = None,
        status: str = "active",
        include_quarantined: bool = False,
    ) -> List[Dict]:
        """按国家查询合规条目。

        保留在 ComplianceRepository 上是兼容旧调用方；读路径实际走
        compliance_index，避免默认查询绕过证据驱动读模型。
        """
        sql = """
            SELECT ci.compliance_id AS id,
                   ci.name,
                   ci.entry_type,
                   ci.mandatory,
                   ci.country_code,
                   ci.status,
                   ci.issuing_body,
                   ci.official_url,
                   ci.applicable_products,
                   ci.effective_date,
                   ci.published_date,
                   ci.summary AS scope_description,
                   ci.summary AS remarks,
                   ci.authenticity_status,
                   ci.authenticity_risk_score,
                   GREATEST(0, 100 - COALESCE(ci.authenticity_risk_score, 0)) AS confidence_score,
                   (ci.authenticity_status = 'verified') AS verified,
                   ci.updated_at,
                   c.name_zh AS country_name,
                   c.priority
            FROM compliance_index ci
            JOIN countries c ON ci.country_code = c.code
            WHERE ci.country_code = %s AND ci.status = %s
        """
        params: list = [country_code, status]
        if not include_quarantined:
            sql += " AND COALESCE(ci.authenticity_status, 'candidate') <> 'quarantined'"
        if entry_type:
            sql += " AND ci.entry_type = %s"
            params.append(entry_type)
        sql += " ORDER BY ci.entry_type, ci.mandatory DESC, ci.name"

        with get_cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    @staticmethod
    def list_by_product(
        product_code: str,
        country_code: Optional[str] = None,
        status: str = "active",
    ) -> List[Dict]:
        """按产品类型查询合规条目（兼容入口，实际读 compliance_index）"""
        sql = """
            SELECT ci.compliance_id AS id,
                   ci.name,
                   ci.entry_type,
                   ci.mandatory,
                   ci.country_code,
                   ci.status,
                   ci.issuing_body,
                   ci.official_url,
                   ci.applicable_products,
                   ci.effective_date,
                   ci.published_date,
                   ci.summary AS scope_description,
                   ci.summary AS remarks,
                   ci.authenticity_status,
                   ci.authenticity_risk_score,
                   GREATEST(0, 100 - COALESCE(ci.authenticity_risk_score, 0)) AS confidence_score,
                   (ci.authenticity_status = 'verified') AS verified,
                   ci.updated_at,
                   c.name_zh AS country_name,
                   c.priority
            FROM compliance_index ci
            JOIN countries c ON ci.country_code = c.code
            WHERE %s = ANY(ci.applicable_products) AND ci.status = %s
              AND COALESCE(ci.authenticity_status, 'candidate') <> 'quarantined'
        """
        params: list = [product_code, status]
        if country_code:
            sql += " AND ci.country_code = %s"
            params.append(country_code)
        sql += " ORDER BY c.priority, ci.mandatory DESC"

        with get_cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    @staticmethod
    def get_upcoming_effective(days: int = 30) -> List[Dict]:
        """获取N天内即将生效的条目"""
        return ComplianceLifecycleRepository.get_upcoming_milestones(days=days, limit=200)

    @staticmethod
    def find_existing(name: str, country_code: str) -> Optional[Dict]:
        """按名称+国家查找已有记录（用于更新比对）"""
        with get_cursor() as cur:
            cur.execute(
                f"""
                SELECT * FROM compliance_knowledge
                WHERE name = %s AND country_code = %s
                LIMIT 1
                """,
                (name, country_code),
            )
            return cur.fetchone()

    @staticmethod
    def search(
        keyword: str,
        country_code: Optional[str] = None,
        product_code: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """全文模糊搜索（兼容入口，实际读 compliance_index）"""
        sql = """
            SELECT ci.compliance_id AS id,
                   ci.name,
                   ci.entry_type,
                   ci.mandatory,
                   ci.country_code,
                   ci.status,
                   ci.issuing_body,
                   ci.official_url,
                   ci.applicable_products,
                   ci.effective_date,
                   ci.published_date,
                   ci.summary AS scope_description,
                   ci.summary AS remarks,
                   ci.authenticity_status,
                   ci.authenticity_risk_score,
                   GREATEST(0, 100 - COALESCE(ci.authenticity_risk_score, 0)) AS confidence_score,
                   (ci.authenticity_status = 'verified') AS verified,
                   ci.updated_at,
                   c.name_zh AS country_name,
                   similarity(ci.name, %s) AS score
            FROM compliance_index ci
            JOIN countries c ON ci.country_code = c.code
            WHERE ci.name % %s AND ci.status = 'active'
              AND COALESCE(ci.authenticity_status, 'candidate') <> 'quarantined'
        """
        params: list = [keyword, keyword]
        if country_code:
            sql += " AND ci.country_code = %s"
            params.append(country_code)
        if product_code:
            sql += " AND %s = ANY(ci.applicable_products)"
            params.append(product_code)
        sql += " ORDER BY score DESC LIMIT %s"
        params.append(limit)

        with get_cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    @staticmethod
    def list_by_ids(record_ids: List[str]) -> List[Dict]:
        if not record_ids:
            return []
        normalized_ids = [str(UUID(str(record_id))) for record_id in record_ids]
        sql = """
            SELECT compliance_id AS id, name, entry_type, country_code
            FROM compliance_index
            WHERE compliance_id = ANY(%s::uuid[])
              AND COALESCE(authenticity_status, 'candidate') <> 'quarantined'
        """
        with get_cursor() as cur:
            cur.execute(sql, (normalized_ids,))
            return [dict(row) for row in cur.fetchall()]

    # ------ 写入 ------

    @staticmethod
    def create(data: Dict[str, Any]) -> str:
        """
        创建新记录，返回新记录 UUID。
        data 中的列表字段自动转为 PostgreSQL 数组。
        """
        _ensure_compliance_create_review_gate(data)
        _normalize_arrays(data)
        _normalize_jsonb(data, ["requirements", "authenticity_reasons"])

        columns = list(data.keys())
        placeholders = [f"%({c})s" for c in columns]

        sql = f"""
            INSERT INTO compliance_knowledge ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING id
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, data)
                new_id = cur.fetchone()[0]

        logger.info("✅ 新增合规记录 [%s] %s", new_id, data.get("name"))
        return str(new_id)

    # 手动编辑时可以修改任何字段，AI更新时走 engine 的保护逻辑
    @staticmethod
    def update(
        record_id: str,
        data: Dict[str, Any],
        version_bump: bool = True,
        force: bool = False,
    ) -> bool:
        """
        更新指定记录，返回是否有实际变更。
        force=True 时跳过保护（手动编辑用）。
        自动递增 version 并更新 updated_at。
        """
        if not data:
            return False

        _normalize_arrays(data)
        _normalize_jsonb(data, ["requirements", "authenticity_reasons"])
        data.pop("id", None)  # 不允许更新主键
        if data.get("verified") is True or data.get("authenticity_status") == VERIFIED_STATUS:
            current = ComplianceRepository.get_by_id(record_id)
            merged = {**dict(current or {}), **data}
            _ensure_verified_review_gate(
                merged,
                VERIFIED_STATUS,
                evidence=data.get("authenticity_evidence") or data.get("evidence_note"),
            )

        set_clauses = []
        params: Dict[str, Any] = {}
        for col, val in data.items():
            if col == "version" and version_bump:
                set_clauses.append(f"{col} = {col} + 1")
                # version 字段通过SQL表达式自增，不加入params
            else:
                set_clauses.append(f"{col} = %({col})s")
                params[col] = val

        params["record_id"] = record_id
        sql = f"""
            UPDATE compliance_knowledge
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = %(record_id)s
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                updated = cur.rowcount > 0

        if updated:
            logger.info("✏️  更新合规记录 [%s]，字段: %s", record_id, list(data.keys()))
        return updated

    @staticmethod
    def update_last_checked(record_ids: List[str]) -> None:
        """批量更新 last_checked 时间（无变更时仅记录检查时间）"""
        if not record_ids:
            return
        with get_connection() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    UPDATE compliance_knowledge SET last_checked = NOW()
                    WHERE id IN %s
                    """,
                    [(tuple(record_ids),)],
                )

    @staticmethod
    def deprecate(record_id: str) -> bool:
        """将记录标记为废止"""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE compliance_knowledge SET status='deprecated', updated_at=NOW() WHERE id=%s",
                    (record_id,),
                )
                return cur.rowcount > 0

    @staticmethod
    def set_authenticity_review(
        record_id: str,
        authenticity_status: str,
        risk_score: int,
        reasons: list[str],
        checked_by: str,
        evidence: Optional[str] = None,
    ) -> bool:
        record = ComplianceRepository.get_by_id(record_id)
        if not record:
            return False
        _ensure_verified_review_gate(dict(record), authenticity_status, evidence=evidence)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE compliance_knowledge
                    SET authenticity_status=%s,
                        authenticity_risk_score=%s,
                        authenticity_reasons=%s,
                        authenticity_checked_at=NOW(),
                        authenticity_checked_by=%s,
                        authenticity_evidence=%s,
                        updated_at=NOW()
                    WHERE id=%s
                    """,
                    (
                        authenticity_status,
                        risk_score,
                        json.dumps(reasons, ensure_ascii=False),
                        checked_by,
                        evidence,
                        record_id,
                    ),
                )
                return cur.rowcount > 0

    @staticmethod
    def mark_source_download_failed(record_id: str, error: str) -> bool:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE compliance_knowledge
                    SET source_download_status='failed',
                        source_download_error=%s,
                        updated_at=NOW()
                    WHERE id=%s
                    """,
                    (error[:1000], record_id),
                )
                return cur.rowcount > 0

    @staticmethod
    def list_pending_source_artifacts(limit: int = 20) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM compliance_knowledge
                WHERE COALESCE(authenticity_status, 'candidate') <> 'quarantined'
                  AND data_source LIKE 'official_source:%%'
                  AND official_url IS NOT NULL
                  AND source_download_status = 'pending'
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def list_downloaded_source_candidates(limit: int = 50) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM compliance_knowledge
                WHERE data_source LIKE 'official_source:%%'
                  AND source_download_status = 'downloaded'
                  AND COALESCE(authenticity_status, 'candidate') IN ('candidate', 'suspicious')
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]


# ============================================================
# 变更日志 Repository
# ============================================================

class ChangeLogRepository:
    """change_log 表的数据访问层"""

    @staticmethod
    def record_change(
        record_id: str,
        change_type: str,
        old_value: Optional[Dict],
        new_value: Optional[Dict],
        changed_fields: Optional[List[str]] = None,
        diff_summary: Optional[str] = None,
        data_source: Optional[str] = None,
    ) -> int:
        """写入变更日志，返回日志 ID"""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO change_log
                        (record_id, change_type, changed_fields, old_value, new_value,
                         diff_summary, data_source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        record_id,
                        change_type,
                        changed_fields,
                        json.dumps(old_value, default=str) if old_value else None,
                        json.dumps(new_value, default=str) if new_value else None,
                        diff_summary,
                        data_source,
                    ),
                )
                log_id = cur.fetchone()[0]
        logger.debug("📝 变更日志 #%d [%s] %s", log_id, change_type, record_id)
        return log_id

    @staticmethod
    def get_pending_review(limit: int = 50) -> List[Dict]:
        """获取待人工审核的变更"""
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT cl.id AS log_id,
                       cl.record_id,
                       ci.name,
                       ci.country_code,
                       c.name_zh AS country_name,
                       cl.change_type,
                       cl.changed_fields,
                       cl.diff_summary,
                       cl.changed_at
                FROM change_log cl
                JOIN compliance_index ci ON cl.record_id = ci.compliance_id
                JOIN countries c ON ci.country_code = c.code
                WHERE cl.reviewed = FALSE
                  AND ci.status='active'
                  AND ci.authenticity_status='verified'
                ORDER BY cl.changed_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()

    @staticmethod
    def mark_reviewed(log_id: int, reviewed_by: str = "admin") -> None:
        """标记变更已审核"""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE change_log
                    SET reviewed=TRUE, reviewed_by=%s, reviewed_at=NOW()
                    WHERE id=%s
                    """,
                    (reviewed_by, log_id),
                )


# ============================================================
# 法规原文结构层 Repository
# ============================================================

class RegulationSectionRepository:
    """regulation_document_sections 表的数据访问层"""

    @staticmethod
    def delete_by_document(doc_id: str) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM regulation_document_sections WHERE document_id=%s",
                    (doc_id,),
                )

    @staticmethod
    def create_sections(doc: Dict[str, Any], sections: List[Dict[str, Any]]) -> None:
        rows = []
        for index, section in enumerate(sections):
            rows.append(
                (
                    doc["id"],
                    int(section.get("section_index", index)),
                    section["section_type"],
                    section["section_ref"],
                    section.get("title"),
                    section.get("section_path"),
                    section["page_from"],
                    section["page_to"],
                    section.get("content") or "",
                    doc["country_code"],
                    doc.get("compliance_id"),
                )
            )
        if not rows:
            return
        with get_connection() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO regulation_document_sections
                        (document_id, section_index, section_type, section_ref, title,
                         section_path, page_from, page_to, content, country_code, compliance_id)
                    VALUES %s
                    """,
                    rows,
                    template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                )

    @staticmethod
    def list_by_document(doc_id: str, limit: int = 100) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, document_id, section_index, section_type, section_ref, title,
                       section_path, page_from, page_to, content, country_code, compliance_id, created_at
                FROM regulation_document_sections
                WHERE document_id=%s
                ORDER BY section_index
                LIMIT %s
                """,
                (doc_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def section_search(
        question: str,
        country_code: Optional[str] = None,
        document_id: Optional[str] = None,
        verified_only: bool = False,
        regime_category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict]:
        section_refs = _extract_query_section_refs(question)
        if section_refs:
            sql = """
                SELECT s.document_id, d.name AS document_name, s.section_index AS chunk_index,
                       s.page_from, s.page_to, s.section_path, s.section_ref AS clause_ref,
                       CASE
                           WHEN s.title IS NOT NULL AND s.title <> '' THEN s.section_ref || ' ' || s.title || E'\n' || s.content
                           ELSE s.section_ref || E'\n' || s.content
                       END AS content,
                       s.country_code, s.compliance_id,
                       1.0 AS section_score
                FROM regulation_document_sections s
                JOIN regulation_documents d ON d.id = s.document_id
                WHERE lower(s.section_ref) = ANY(%s)
            """
            params: List[Any] = [[ref.lower() for ref in section_refs]]
            if country_code:
                sql += f" AND {_jurisdiction_scope_filter_sql('s.country_code')}"
                params.extend([country_code, country_code])
            if document_id:
                sql += " AND s.document_id = %s"
                params.append(document_id)
            if verified_only:
                sql += f" AND {_verified_document_filter_sql('s.document_id')}"
            if regime_category:
                sql += f" AND {_document_regime_filter_sql('s.document_id')}"
                params.append(regime_category)
            sql += " ORDER BY s.page_from, s.section_index LIMIT %s"
            params.append(limit)
            with get_cursor() as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
        return []


# ============================================================
# 法规原文切片 Repository
# ============================================================

class RegulationChunkRepository:
    """regulation_document_chunks 表的数据访问层"""

    @staticmethod
    def resolve_ready_document_scope(doc_id: Optional[str]) -> Optional[str]:
        """Return a searchable ready document for the same compliance item.

        The public read model can temporarily point at an older failed artifact
        after a replacement official PDF is imported. RAG should not stay pinned
        to a zero-chunk document when the same verified compliance item already
        has a ready indexed document.
        """
        if not doc_id:
            return doc_id
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM regulation_documents
                WHERE id = %s
                  AND index_status = 'ready'
                  AND COALESCE(chunk_count, 0) > 0
                LIMIT 1
                """,
                (doc_id,),
            )
            current = cur.fetchone()
            if current:
                return str(current["id"])

            cur.execute(
                """
                SELECT replacement.id
                FROM regulation_documents original
                JOIN regulation_documents replacement
                  ON replacement.compliance_id = original.compliance_id
                WHERE original.id = %s
                  AND replacement.index_status = 'ready'
                  AND COALESCE(replacement.chunk_count, 0) > 0
                ORDER BY replacement.created_at DESC
                LIMIT 1
                """,
                (doc_id,),
            )
            replacement = cur.fetchone()
            return str(replacement["id"]) if replacement else doc_id

    @staticmethod
    def delete_by_document(doc_id: str) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM regulation_document_chunks WHERE document_id=%s",
                    (doc_id,),
                )

    @staticmethod
    def create_chunks(doc: Dict[str, Any], chunks: List[Dict[str, Any]], vectors: List[List[float]]) -> None:
        rows = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            rows.append(
                (
                    doc["id"],
                    index,
                    chunk["page_from"],
                    chunk["page_to"],
                    chunk.get("section_path"),
                    chunk.get("clause_ref"),
                    chunk["content"],
                    f"[{','.join(str(value) for value in vector)}]",
                    doc["country_code"],
                    doc.get("compliance_id"),
                )
            )
        with get_connection() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO regulation_document_chunks
                        (document_id, chunk_index, page_from, page_to, section_path,
                         clause_ref, content, embedding, country_code, compliance_id)
                    VALUES %s
                    """,
                    rows,
                    template="(%s,%s,%s,%s,%s,%s,%s,%s::vector,%s,%s)",
                )

    @staticmethod
    def list_by_document(doc_id: str, limit: int = 50) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, document_id, chunk_index, page_from, page_to, section_path,
                       clause_ref, content, country_code, compliance_id, created_at
                FROM regulation_document_chunks
                WHERE document_id=%s
                ORDER BY chunk_index
                LIMIT %s
                """,
                (doc_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def list_by_ids(chunk_ids: List[str]) -> List[Dict]:
        if not chunk_ids:
            return []
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.document_id, d.name AS document_name, c.chunk_index,
                       c.page_from, c.page_to, c.section_path, c.clause_ref,
                       c.content, c.country_code, c.compliance_id, c.created_at
                FROM regulation_document_chunks c
                JOIN regulation_documents d ON d.id = c.document_id
                WHERE c.id = ANY(%s::uuid[])
                """,
                (chunk_ids,),
            )
            rows = [dict(row) for row in cur.fetchall()]
        order = {str(chunk_id): index for index, chunk_id in enumerate(chunk_ids)}
        return sorted(rows, key=lambda row: order.get(str(row.get("id")), len(order)))

    @staticmethod
    def list_by_document_pages(document_id: str, pages: List[int], limit: int = 3) -> List[Dict]:
        if not document_id or not pages:
            return []
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.document_id, d.name AS document_name, c.chunk_index,
                       c.page_from, c.page_to, c.section_path, c.clause_ref,
                       c.content, c.country_code, c.compliance_id, c.created_at
                FROM regulation_document_chunks c
                JOIN regulation_documents d ON d.id = c.document_id
                WHERE c.document_id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM unnest(%s::int[]) AS p(page_no)
                      WHERE p.page_no BETWEEN c.page_from AND c.page_to
                  )
                ORDER BY c.chunk_index
                LIMIT %s
                """,
                (document_id, pages, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def keyword_search(
        keyword: str,
        country_code: Optional[str] = None,
        document_id: Optional[str] = None,
        verified_only: bool = False,
        regime_category: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        sql = """
            SELECT c.document_id, d.name AS document_name, c.chunk_index, c.page_from, c.page_to,
                   c.section_path, c.clause_ref, c.content, c.country_code, c.compliance_id,
                   ts_rank_cd(c.content_tsv, plainto_tsquery('simple', %s)) AS keyword_score
            FROM regulation_document_chunks c
            JOIN regulation_documents d ON d.id = c.document_id
            WHERE c.content_tsv @@ plainto_tsquery('simple', %s)
        """
        params: List[Any] = [keyword, keyword]
        if country_code:
            sql += f" AND {_jurisdiction_scope_filter_sql('c.country_code')}"
            params.extend([country_code, country_code])
        if document_id:
            sql += " AND c.document_id = %s"
            params.append(document_id)
        if verified_only:
            sql += f" AND {_verified_document_filter_sql('c.document_id')}"
        if regime_category:
            sql += f" AND {_document_regime_filter_sql('c.document_id')}"
            params.append(regime_category)
        sql += " ORDER BY keyword_score DESC, c.created_at DESC LIMIT %s"
        params.append(limit)

        with get_cursor() as cur:
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()]
        if rows or not RegulationChunkRepository._contains_cjk(keyword):
            return rows
        return RegulationChunkRepository._cjk_keyword_search(
            keyword=keyword,
            country_code=country_code,
            document_id=document_id,
            verified_only=verified_only,
            regime_category=regime_category,
            limit=limit,
        )

    @staticmethod
    def _cjk_keyword_search(
        keyword: str,
        country_code: Optional[str] = None,
        document_id: Optional[str] = None,
        verified_only: bool = False,
        regime_category: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        terms = RegulationChunkRepository._cjk_keyword_terms(keyword)
        if not terms:
            return []
        score_parts = []
        score_params: List[Any] = []
        where_parts = []
        where_params: List[Any] = []
        for term in terms:
            pattern = f"%{term}%"
            score_parts.append("CASE WHEN c.content ILIKE %s OR d.name ILIKE %s THEN 0.15 ELSE 0 END")
            score_params.extend([pattern, pattern])
            where_parts.append("(c.content ILIKE %s OR d.name ILIKE %s)")
            where_params.extend([pattern, pattern])
        sql = f"""
            SELECT c.document_id, d.name AS document_name, c.chunk_index, c.page_from, c.page_to,
                   c.section_path, c.clause_ref, c.content, c.country_code, c.compliance_id,
                   ({' + '.join(score_parts)}) AS keyword_score
            FROM regulation_document_chunks c
            JOIN regulation_documents d ON d.id = c.document_id
            WHERE ({' OR '.join(where_parts)})
        """
        params: List[Any] = [*score_params, *where_params]
        if country_code:
            sql += f" AND {_jurisdiction_scope_filter_sql('c.country_code')}"
            params.extend([country_code, country_code])
        if document_id:
            sql += " AND c.document_id = %s"
            params.append(document_id)
        if verified_only:
            sql += f" AND {_verified_document_filter_sql('c.document_id')}"
        if regime_category:
            sql += f" AND {_document_regime_filter_sql('c.document_id')}"
            params.append(regime_category)
        sql += " ORDER BY keyword_score DESC, c.created_at DESC LIMIT %s"
        params.append(limit)

        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def _contains_cjk(value: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", value or ""))

    @staticmethod
    def _cjk_keyword_terms(keyword: str) -> List[str]:
        raw_terms = re.split(r"[\s,，、;；]+", keyword or "")
        aliases = []
        if "专用网络安全产品" in (keyword or ""):
            aliases.append("网络安全专用产品")
        stop_terms = {"安全", "要求", "产品", "有哪些", "什么"}
        terms: List[str] = []
        for term in [*raw_terms, *aliases]:
            cleaned = term.strip()
            if not cleaned or cleaned in stop_terms:
                continue
            if len(cleaned) < 2:
                continue
            if cleaned not in terms:
                terms.append(cleaned)
        return terms[:10]

    @staticmethod
    def vector_search(
        query_vector: List[float],
        country_code: Optional[str] = None,
        document_id: Optional[str] = None,
        verified_only: bool = False,
        regime_category: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        vector_literal = f"[{','.join(str(value) for value in query_vector)}]"
        sql = """
            SELECT c.document_id, d.name AS document_name, c.chunk_index, c.page_from, c.page_to,
                   c.section_path, c.clause_ref, c.content, c.country_code, c.compliance_id,
                   1 - (c.embedding <=> %s::vector) AS vector_score
            FROM regulation_document_chunks c
            JOIN regulation_documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
        """
        params: List[Any] = [vector_literal]
        if country_code:
            sql += f" AND {_jurisdiction_scope_filter_sql('c.country_code')}"
            params.extend([country_code, country_code])
        if document_id:
            sql += " AND c.document_id = %s"
            params.append(document_id)
        if verified_only:
            sql += f" AND {_verified_document_filter_sql('c.document_id')}"
        if regime_category:
            sql += f" AND {_document_regime_filter_sql('c.document_id')}"
            params.append(regime_category)
        sql += " ORDER BY c.embedding <=> %s::vector ASC LIMIT %s"
        params.extend([vector_literal, limit])

        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


class RegulationSpecRequirementRepository:
    """regulation_spec_requirements 表的数据访问层"""

    _VARCHAR_LIMITS = {
        "regulation_name": 300,
        "req_id": 80,
        "module_zh": 120,
        "module_en": 120,
        "title_zh": 200,
        "title_en": 200,
        "mandatory": 20,
        "priority": 10,
        "regulation_clause": 120,
        "source_pages": 120,
    }

    @staticmethod
    def _clamp(value: Any, limit: int) -> Any:
        if value is None or not isinstance(value, str):
            return value
        return value[:limit]

    @staticmethod
    def upsert_many(rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0

        payloads: List[tuple[Any, ...]] = []
        for row in rows:
            varchar = {
                key: RegulationSpecRequirementRepository._clamp(row.get(key), limit)
                for key, limit in RegulationSpecRequirementRepository._VARCHAR_LIMITS.items()
            }
            payloads.append(
                (
                    row["document_id"],
                    row.get("compliance_id"),
                    row["country_code"],
                    varchar["regulation_name"],
                    varchar["req_id"],
                    varchar["module_zh"],
                    varchar["module_en"],
                    varchar["title_zh"],
                    varchar["title_en"],
                    row.get("description_zh"),
                    row.get("description_en"),
                    row.get("applicable_products") or [],
                    varchar["mandatory"],
                    varchar["priority"],
                    varchar["regulation_clause"],
                    row.get("verification_method_zh"),
                    row.get("verification_method_en"),
                    row.get("notes_zh"),
                    row.get("notes_en"),
                    varchar["source_pages"],
                    row.get("source_chunk_ids") or [],
                )
            )

        with get_connection() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    INSERT INTO regulation_spec_requirements
                        (document_id, compliance_id, country_code, regulation_name, req_id,
                         module_zh, module_en, title_zh, title_en, description_zh, description_en,
                         applicable_products, mandatory, priority, regulation_clause,
                         verification_method_zh, verification_method_en, notes_zh, notes_en,
                         source_pages, source_chunk_ids)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid[])
                    ON CONFLICT (document_id, req_id) DO UPDATE
                    SET compliance_id=EXCLUDED.compliance_id,
                        country_code=EXCLUDED.country_code,
                        regulation_name=EXCLUDED.regulation_name,
                        module_zh=EXCLUDED.module_zh,
                        module_en=EXCLUDED.module_en,
                        title_zh=EXCLUDED.title_zh,
                        title_en=EXCLUDED.title_en,
                        description_zh=EXCLUDED.description_zh,
                        description_en=EXCLUDED.description_en,
                        applicable_products=EXCLUDED.applicable_products,
                        mandatory=EXCLUDED.mandatory,
                        priority=EXCLUDED.priority,
                        regulation_clause=EXCLUDED.regulation_clause,
                        verification_method_zh=EXCLUDED.verification_method_zh,
                        verification_method_en=EXCLUDED.verification_method_en,
                        notes_zh=EXCLUDED.notes_zh,
                        notes_en=EXCLUDED.notes_en,
                        source_pages=EXCLUDED.source_pages,
                        source_chunk_ids=EXCLUDED.source_chunk_ids,
                        updated_at=NOW()
                    """,
                    payloads,
                    page_size=100,
                )
        return len(rows)

    @staticmethod
    def list_filtered(
        document_id: Optional[str] = None,
        country_code: Optional[str] = None,
        product_code: Optional[str] = None,
        priority: Optional[str] = None,
        regulation_clause: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict]:
        sql = """
            SELECT *
            FROM regulation_spec_requirements
            WHERE 1=1
        """
        params: List[Any] = []
        if document_id:
            sql += " AND document_id = %s"
            params.append(document_id)
        if country_code:
            sql += " AND country_code = %s"
            params.append(country_code)
        if product_code:
            sql += " AND %s = ANY(applicable_products)"
            params.append(product_code)
        if priority:
            sql += " AND priority = %s"
            params.append(priority)
        if regulation_clause:
            sql += " AND regulation_clause ILIKE %s"
            params.append(f"%{regulation_clause}%")
        sql += " ORDER BY priority NULLS LAST, req_id LIMIT %s"
        params.append(limit)
        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def search_for_rag(
        question: str,
        country_code: Optional[str] = None,
        product_code: Optional[str] = None,
        document_id: Optional[str] = None,
        verified_only: bool = True,
        limit: int = 20,
    ) -> List[Dict]:
        terms = RegulationSpecRequirementRepository._rag_terms(question)
        sql = """
            SELECT r.*,
                   (
                       CASE WHEN r.priority = 'P0' THEN 0.35
                            WHEN r.priority = 'P1' THEN 0.25
                            ELSE 0.1 END
                       + CASE WHEN r.mandatory = 'mandatory' THEN 0.2 ELSE 0.0 END
                       + CASE WHEN cardinality(r.source_chunk_ids) > 0 THEN 0.35 ELSE 0.0 END
                       + CASE WHEN %s IS NOT NULL AND %s = ANY(r.applicable_products) THEN 0.2 ELSE 0.0 END
                   ) AS spec_score
            FROM regulation_spec_requirements r
            WHERE 1=1
        """
        params: List[Any] = [product_code, product_code]
        if country_code:
            sql += f" AND {_jurisdiction_scope_filter_sql('r.country_code')}"
            params.extend([country_code, country_code])
        if product_code:
            sql += " AND (%s = ANY(r.applicable_products) OR cardinality(r.applicable_products) = 0)"
            params.append(product_code)
        if document_id:
            sql += " AND r.document_id = %s"
            params.append(document_id)
        sql += """
            AND (
                cardinality(r.source_chunk_ids) > 0
                OR (r.source_pages IS NOT NULL AND btrim(r.source_pages) <> '')
            )
        """
        if verified_only:
            sql += f" AND {_verified_document_filter_sql('r.document_id')}"
        if terms:
            sql += """
                AND (
                    concat_ws(' ',
                        r.regulation_name, r.req_id, r.module_zh, r.module_en,
                        r.title_zh, r.title_en, r.description_zh, r.description_en,
                        r.verification_method_zh, r.verification_method_en,
                        r.regulation_clause, array_to_string(r.applicable_products, ' ')
                    ) ILIKE ANY(%s)
                )
            """
            params.append([f"%{term}%" for term in terms])
        sql += """
            ORDER BY spec_score DESC, r.priority NULLS LAST, r.updated_at DESC
            LIMIT %s
        """
        params.append(limit)
        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def _rag_terms(question: str) -> List[str]:
        raw = (question or "").strip()
        terms: List[str] = []
        lowered = raw.lower()
        if raw:
            terms.append(raw[:80])
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", raw):
            terms.append(token)
        if any(marker in lowered for marker in ("交换机", "路由器", "网络设备", "network device", "router", "switch")):
            terms.extend(["Network Device", "Network Devices", "router", "switch", "Protection Profile"])
        if any(marker in lowered for marker in ("默认安全", "漏洞", "更新", "security update", "vulnerab")):
            terms.extend(["security update", "vulnerability", "secure by default"])
        seen = set()
        result = []
        for term in terms:
            normalized = str(term).strip()
            key = normalized.lower()
            if normalized and key not in seen:
                seen.add(key)
                result.append(normalized)
        return result[:12]

    @staticmethod
    def count_by_document(document_id: str) -> int:
        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM regulation_spec_requirements WHERE document_id=%s",
                (document_id,),
            )
            row = cur.fetchone()
            return int(row["cnt"]) if row else 0


# ============================================================
# 证据驱动重构 Repository
# ============================================================


class SourceRecordRepository:
    @staticmethod
    def upsert_candidate(
        country_code: str,
        title: str,
        entry_type: str,
        source_url: Optional[str],
        artifact_url: Optional[str],
        published_date: Optional[Any],
        official_source_id: Optional[str] = None,
        compliance_id: Optional[str] = None,
        discovery_method: str = "official_source",
        source_payload: Optional[Dict[str, Any]] = None,
        source_status: str = "candidate",
    ) -> str:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_records
                        (official_source_id, compliance_id, country_code, title, entry_type,
                         discovery_method, source_url, artifact_url, published_date, source_status, source_payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (country_code, title, COALESCE(source_url, ''))
                    DO UPDATE
                    SET official_source_id=EXCLUDED.official_source_id,
                        compliance_id=COALESCE(source_records.compliance_id, EXCLUDED.compliance_id),
                        artifact_url=COALESCE(EXCLUDED.artifact_url, source_records.artifact_url),
                        published_date=COALESCE(EXCLUDED.published_date, source_records.published_date),
                        source_status=EXCLUDED.source_status,
                        source_payload=COALESCE(EXCLUDED.source_payload, source_records.source_payload),
                        updated_at=NOW()
                    RETURNING id
                    """,
                    (
                        official_source_id,
                        compliance_id,
                        country_code,
                        title,
                        entry_type,
                        discovery_method,
                        source_url,
                        artifact_url,
                        published_date,
                        source_status,
                        json.dumps(source_payload or {}, ensure_ascii=False),
                    ),
                )
                return str(cur.fetchone()[0])

    @staticmethod
    def get_by_id(source_record_id: str) -> Optional[Dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM source_records WHERE id=%s", (source_record_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_validation(
        source_record_id: str,
        *,
        source_status: str,
        validation_stage: Dict[str, Any],
    ) -> bool:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE source_records
                    SET source_status=%s,
                        source_payload=jsonb_set(
                            COALESCE(source_payload, '{}'::jsonb),
                            '{validation_stage}',
                            %s::jsonb,
                            TRUE
                        ),
                        updated_at=NOW()
                    WHERE id=%s
                    """,
                    (
                        source_status,
                        json.dumps(validation_stage, ensure_ascii=False),
                        source_record_id,
                    ),
                )
                return cur.rowcount > 0

    @staticmethod
    def get_by_compliance_id(compliance_id: str) -> Optional[Dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM source_records WHERE compliance_id=%s ORDER BY updated_at DESC LIMIT 1", (compliance_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_pending_artifact_records(limit: int = 20) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                f"""
                SELECT sr.*,
                       sa.id AS source_artifact_id,
                       sa.download_status,
                       sa.download_error
                FROM source_records sr
                LEFT JOIN source_artifacts sa
                  ON sa.source_record_id = sr.id
                WHERE sr.source_status='candidate'
                  AND COALESCE(sr.artifact_url, sr.source_url) IS NOT NULL
                  {source_record_not_verified_filter_sql("sr")}
                  AND (
                        sa.id IS NULL
                        OR sa.download_status IN ('pending', 'failed')
                  )
                ORDER BY sr.updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def list_bucketable_records(limit: int = 50) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT sr.*
                FROM source_records sr
                JOIN source_artifacts sa
                  ON sa.source_record_id = sr.id
                WHERE sr.compliance_id IS NOT NULL
                  AND sa.download_status='downloaded'
                ORDER BY sr.updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def attach_compliance(source_record_id: str, compliance_id: str) -> bool:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE source_records
                    SET compliance_id=%s,
                        updated_at=NOW()
                    WHERE id=%s
                    """,
                    (compliance_id, source_record_id),
                )
                return cur.rowcount > 0


class SourceArtifactRepository:
    @staticmethod
    def get_by_source_record_id(source_record_id: str) -> Optional[Dict]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM source_artifacts
                WHERE source_record_id=%s
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (source_record_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def upsert_for_compliance(
        compliance_id: Optional[str],
        official_url: Optional[str],
        artifact_url: Optional[str],
        artifact_type: Optional[str],
        artifact_sha256: Optional[str],
        download_status: str,
        download_error: Optional[str],
        document_id: Optional[str] = None,
        source_record_id: Optional[str] = None,
    ) -> str:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_artifacts
                        (source_record_id, compliance_id, document_id, official_url, artifact_url,
                         artifact_type, artifact_sha256, download_status, download_error, downloaded_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,
                            CASE WHEN %s='downloaded' THEN NOW() ELSE NULL END)
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                    (
                        source_record_id,
                        compliance_id,
                        document_id,
                        official_url,
                        artifact_url,
                        artifact_type,
                        artifact_sha256,
                        download_status,
                        (download_error or "")[:1000] or None,
                        download_status,
                    ),
                )
                row = cur.fetchone()
                if row:
                    return str(row[0])

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id FROM source_artifacts
                    WHERE compliance_id=%s
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    (compliance_id,),
                )
                existing = cur.fetchone()
                if not existing:
                    raise RuntimeError("source_artifact upsert failed")
                artifact_id = str(existing[0])

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE source_artifacts
                    SET source_record_id=COALESCE(%s, source_record_id),
                        document_id=COALESCE(%s, document_id),
                        official_url=COALESCE(%s, official_url),
                        artifact_url=COALESCE(%s, artifact_url),
                        artifact_type=COALESCE(%s, artifact_type),
                        artifact_sha256=COALESCE(%s, artifact_sha256),
                        download_status=%s,
                        download_error=%s,
                        downloaded_at=CASE WHEN %s='downloaded' THEN COALESCE(downloaded_at, NOW()) ELSE downloaded_at END,
                        updated_at=NOW()
                    WHERE id=%s
                    """,
                    (
                        source_record_id,
                        document_id,
                        official_url,
                        artifact_url,
                        artifact_type,
                        artifact_sha256,
                        download_status,
                        (download_error or "")[:1000] or None,
                        download_status,
                        artifact_id,
                    ),
                )
            return artifact_id

    @staticmethod
    def list_by_entity(entity_id: str) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT * FROM source_artifacts
                WHERE compliance_id=%s OR source_record_id=%s OR document_id=%s
                ORDER BY created_at DESC
                """,
                (entity_id, entity_id, entity_id),
            )
            return [dict(row) for row in cur.fetchall()]


class CanonicalRequirementRepository:
    @staticmethod
    def upsert_from_compliance(
        record: Dict[str, Any],
        verification_status: str,
        source_record_id: Optional[str] = None,
        source_artifact_id: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> str:
        payload = {
            "technical_standards": record.get("technical_standards"),
            "regulation_basis": record.get("regulation_basis"),
            "scope_description": record.get("scope_description"),
            "requirements": record.get("requirements"),
            "assessment_procedure": record.get("assessment_procedure"),
            "remarks": record.get("remarks"),
            "applicable_products": record.get("applicable_products"),
        }
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO canonical_requirements
                        (compliance_id, source_record_id, source_artifact_id, document_id,
                         country_code, name, entry_type, mandatory, issuing_body, official_url,
                         verification_status, requirement_payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (compliance_id)
                    DO UPDATE
                    SET source_record_id=COALESCE(EXCLUDED.source_record_id, canonical_requirements.source_record_id),
                        source_artifact_id=COALESCE(EXCLUDED.source_artifact_id, canonical_requirements.source_artifact_id),
                        document_id=COALESCE(EXCLUDED.document_id, canonical_requirements.document_id),
                        country_code=EXCLUDED.country_code,
                        name=EXCLUDED.name,
                        entry_type=EXCLUDED.entry_type,
                        mandatory=EXCLUDED.mandatory,
                        issuing_body=EXCLUDED.issuing_body,
                        official_url=EXCLUDED.official_url,
                        verification_status=EXCLUDED.verification_status,
                        requirement_payload=EXCLUDED.requirement_payload,
                        updated_at=NOW()
                    RETURNING id
                    """,
                    (
                        record.get("id"),
                        source_record_id,
                        source_artifact_id,
                        document_id,
                        record["country_code"],
                        record["name"],
                        record["entry_type"],
                        record.get("mandatory"),
                        record.get("issuing_body"),
                        record.get("official_url"),
                        verification_status,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
                return str(cur.fetchone()[0])

    @staticmethod
    def upsert_parse_candidate(doc: Dict[str, Any], entry: Dict[str, Any]) -> str:
        record = {
            "id": doc.get("compliance_id"),
            "country_code": entry["country_code"],
            "name": entry["name"],
            "entry_type": entry["entry_type"],
            "mandatory": entry.get("mandatory"),
            "issuing_body": entry.get("issuing_body"),
            "official_url": doc.get("cos_url"),
            "technical_standards": entry.get("technical_standards"),
            "regulation_basis": entry.get("regulation_basis"),
            "scope_description": entry.get("scope_description"),
            "requirements": entry.get("requirements"),
            "assessment_procedure": entry.get("assessment_procedure"),
            "remarks": entry.get("remarks"),
            "applicable_products": entry.get("applicable_products"),
        }
        return CanonicalRequirementRepository.upsert_from_compliance(
            record,
            verification_status="candidate",
            document_id=str(doc["id"]),
        )

    @staticmethod
    def get_by_compliance_id(compliance_id: str) -> Optional[Dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM canonical_requirements WHERE compliance_id=%s", (compliance_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_by_document_id(document_id: str) -> Optional[Dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM canonical_requirements WHERE document_id=%s ORDER BY updated_at DESC LIMIT 1", (document_id,))
            row = cur.fetchone()
            return dict(row) if row else None


class ReviewCaseRepository:
    @staticmethod
    def ensure_for_record(record: Dict[str, Any]) -> str:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO review_cases
                        (compliance_id, current_status, risk_score, reasons, evidence_note,
                         source_download_status, source_download_error, checked_at, checked_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (compliance_id)
                    DO UPDATE
                    SET current_status=EXCLUDED.current_status,
                        risk_score=EXCLUDED.risk_score,
                        reasons=EXCLUDED.reasons,
                        evidence_note=COALESCE(EXCLUDED.evidence_note, review_cases.evidence_note),
                        source_download_status=COALESCE(EXCLUDED.source_download_status, review_cases.source_download_status),
                        source_download_error=COALESCE(EXCLUDED.source_download_error, review_cases.source_download_error),
                        checked_at=COALESCE(EXCLUDED.checked_at, review_cases.checked_at),
                        checked_by=COALESCE(EXCLUDED.checked_by, review_cases.checked_by),
                        updated_at=NOW()
                    RETURNING id
                    """,
                    (
                        record["id"],
                        record.get("authenticity_status") or "candidate",
                        int(record.get("authenticity_risk_score") or 0),
                        json.dumps(record.get("authenticity_reasons") or [], ensure_ascii=False),
                        record.get("authenticity_evidence"),
                        record.get("source_download_status"),
                        record.get("source_download_error"),
                        record.get("authenticity_checked_at"),
                        record.get("authenticity_checked_by"),
                    ),
                )
                return str(cur.fetchone()[0])

    @staticmethod
    def apply_decision(
        compliance_id: str,
        authenticity_status: str,
        risk_score: int,
        reasons: List[str],
        evidence_note: str,
        checked_by: str,
        source_download_status: Optional[str] = None,
        source_download_error: Optional[str] = None,
        canonical_requirement_id: Optional[str] = None,
        source_record_id: Optional[str] = None,
    ) -> str:
        existing = ReviewCaseRepository.get_by_compliance_id(compliance_id)
        previous_status = existing.get("current_status") if existing else None
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO review_cases
                        (compliance_id, source_record_id, canonical_requirement_id, current_status, risk_score,
                         reasons, evidence_note, source_download_status, source_download_error,
                         checked_at, checked_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s)
                    ON CONFLICT (compliance_id)
                    DO UPDATE
                    SET source_record_id=COALESCE(EXCLUDED.source_record_id, review_cases.source_record_id),
                        canonical_requirement_id=COALESCE(EXCLUDED.canonical_requirement_id, review_cases.canonical_requirement_id),
                        current_status=EXCLUDED.current_status,
                        risk_score=EXCLUDED.risk_score,
                        reasons=EXCLUDED.reasons,
                        evidence_note=EXCLUDED.evidence_note,
                        source_download_status=COALESCE(EXCLUDED.source_download_status, review_cases.source_download_status),
                        source_download_error=COALESCE(EXCLUDED.source_download_error, review_cases.source_download_error),
                        checked_at=NOW(),
                        checked_by=EXCLUDED.checked_by,
                        updated_at=NOW()
                    RETURNING id
                    """,
                    (
                        compliance_id,
                        source_record_id,
                        canonical_requirement_id,
                        authenticity_status,
                        risk_score,
                        json.dumps(reasons, ensure_ascii=False),
                        evidence_note,
                        source_download_status,
                        (source_download_error or "")[:1000] or None,
                        checked_by,
                    ),
                )
                review_case_id = str(cur.fetchone()[0])
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO review_events
                        (review_case_id, compliance_id, event_type, from_status, to_status, event_payload, checked_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        review_case_id,
                        compliance_id,
                        "decision",
                        previous_status,
                        authenticity_status,
                        json.dumps(
                            {
                                "risk_score": risk_score,
                                "reasons": reasons,
                                "evidence_note": evidence_note,
                                "source_download_status": source_download_status,
                                "source_download_error": source_download_error,
                            },
                            ensure_ascii=False,
                        ),
                        checked_by,
                    ),
                )
        return review_case_id

    @staticmethod
    def list_cases(
        current_status: Optional[str] = None,
        country_code: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        sql = """
            SELECT rc.*,
                   ci.name AS title,
                   ci.country_code,
                   ci.entry_type,
                   ci.official_url
            FROM review_cases rc
            LEFT JOIN compliance_index ci ON ci.compliance_id = rc.compliance_id
            WHERE 1=1
        """
        params: List[Any] = []
        if current_status:
            sql += " AND rc.current_status=%s"
            params.append(current_status)
        if country_code:
            sql += " AND ci.country_code=%s"
            params.append(country_code)
        sql += " ORDER BY rc.updated_at DESC LIMIT %s"
        params.append(limit)
        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def get_by_compliance_id(compliance_id: str) -> Optional[Dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM review_cases WHERE compliance_id=%s", (compliance_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_by_id(case_id: str) -> Optional[Dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM review_cases WHERE id=%s", (case_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_events(case_id: str) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM review_events WHERE review_case_id=%s ORDER BY created_at DESC", (case_id,))
            return [dict(row) for row in cur.fetchall()]


class ComplianceIndexRepository:
    @staticmethod
    def list_for_verification(
        current_status: str = "suspicious",
        country_code: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        params: List[Any] = [current_status]
        sql = """
            SELECT compliance_id::TEXT AS compliance_id,
                   country_code,
                   name,
                   entry_type,
                   mandatory,
                   official_url,
                   summary
            FROM compliance_index
            WHERE authenticity_status=%s
        """
        if country_code:
            sql += " AND country_code=%s"
            params.append(country_code.upper())
        sql += """
            ORDER BY
              CASE WHEN COALESCE(official_url, '') <> '' THEN 0 ELSE 1 END,
              updated_at DESC
            LIMIT %s
        """
        params.append(limit)
        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def refresh_for_compliance(record: Dict[str, Any]) -> str:
        review_case = ReviewCaseRepository.get_by_compliance_id(str(record["id"]))
        canonical = CanonicalRequirementRepository.get_by_compliance_id(str(record["id"]))
        artifacts = SourceArtifactRepository.list_by_entity(str(record["id"]))
        source_record = SourceRecordRepository.get_by_compliance_id(str(record["id"]))
        source_artifact_id = artifacts[0]["id"] if artifacts else None
        review_case_id = review_case["id"] if review_case else None
        canonical_id = canonical["id"] if canonical else None
        source_record_id = source_record["id"] if source_record else None
        authenticity_status = (
            review_case.get("current_status")
            if review_case
            else record.get("authenticity_status") or "candidate"
        )
        risk_score = (
            int(review_case.get("risk_score") or 0)
            if review_case
            else int(record.get("authenticity_risk_score") or 0)
        )
        summary = record.get("scope_description") or record.get("remarks")
        regime_category = classify_regime_category({**record, "summary": summary})
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO compliance_index
                        (compliance_id, canonical_requirement_id, review_case_id, source_record_id, source_artifact_id,
                         document_id, country_code, name, entry_type, mandatory, status, issuing_body, official_url,
                         authenticity_status, authenticity_risk_score, applicable_products,
                         effective_date, published_date, summary, regime_category)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (compliance_id)
                    DO UPDATE
                    SET canonical_requirement_id=EXCLUDED.canonical_requirement_id,
                        review_case_id=EXCLUDED.review_case_id,
                        source_record_id=EXCLUDED.source_record_id,
                        source_artifact_id=EXCLUDED.source_artifact_id,
                        document_id=EXCLUDED.document_id,
                        country_code=EXCLUDED.country_code,
                        name=EXCLUDED.name,
                        entry_type=EXCLUDED.entry_type,
                        mandatory=EXCLUDED.mandatory,
                        status=EXCLUDED.status,
                        issuing_body=EXCLUDED.issuing_body,
                        official_url=EXCLUDED.official_url,
                        authenticity_status=EXCLUDED.authenticity_status,
                        authenticity_risk_score=EXCLUDED.authenticity_risk_score,
                        applicable_products=EXCLUDED.applicable_products,
                        effective_date=EXCLUDED.effective_date,
                        published_date=EXCLUDED.published_date,
                        summary=EXCLUDED.summary,
                        regime_category=EXCLUDED.regime_category,
                        updated_at=NOW()
                    RETURNING id
                    """,
                    (
                        record["id"],
                        canonical_id,
                        review_case_id,
                        source_record_id,
                        source_artifact_id,
                        record.get("source_document_id"),
                        record["country_code"],
                        record["name"],
                        record["entry_type"],
                        record.get("mandatory"),
                        record.get("status"),
                        record.get("issuing_body"),
                        record.get("official_url"),
                        authenticity_status,
                        risk_score,
                        record.get("applicable_products") or [],
                        record.get("effective_date"),
                        record.get("published_date"),
                        summary,
                        regime_category,
                    ),
                )
                return str(cur.fetchone()[0])

    @staticmethod
    def list_filtered(
        country_code: Optional[str] = None,
        entry_type: Optional[str] = None,
        mandatory: Optional[str] = None,
        status: Optional[str] = "active",
        product_code: Optional[str] = None,
        keyword: Optional[str] = None,
        authenticity_status: Optional[str] = None,
        regime_category: Optional[str] = None,
        include_inherited: bool = False,
        include_suspicious: bool = True,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        if country_code and include_inherited:
            sql = """
                WITH jurisdiction_scope AS (
                    SELECT
                        %s::varchar AS source_code,
                        'local'::text AS scope_origin,
                        NULL::varchar AS inherited_from_code,
                        NULL::text AS inheritance_reason
                    UNION ALL
                    SELECT
                        ji.parent_code AS source_code,
                        'inherited'::text AS scope_origin,
                        ji.parent_code AS inherited_from_code,
                        ji.reason AS inheritance_reason
                    FROM jurisdiction_inheritance ji
                    WHERE ji.child_code = %s
                      AND ji.enabled = TRUE
                      AND (ji.effective_to IS NULL OR ji.effective_to >= CURRENT_DATE)
                )
                SELECT ci.*, js.scope_origin, js.inherited_from_code, js.inheritance_reason
                FROM compliance_index ci
                JOIN jurisdiction_scope js ON js.source_code = ci.country_code
                WHERE 1=1
            """
            params: List[Any] = [country_code, country_code]
        else:
            sql = """
                SELECT
                    ci.*,
                    'local'::text AS scope_origin,
                    NULL::varchar AS inherited_from_code,
                    NULL::text AS inheritance_reason
                FROM compliance_index ci
                WHERE 1=1
            """
            params = []
        if country_code and not include_inherited:
            sql += " AND ci.country_code=%s"; params.append(country_code)
        if entry_type:
            sql += " AND ci.entry_type=%s"; params.append(entry_type)
        if mandatory:
            sql += " AND ci.mandatory=%s"; params.append(mandatory)
        if status:
            sql += " AND ci.status=%s"; params.append(status)
        if product_code:
            sql += " AND %s = ANY(ci.applicable_products)"; params.append(product_code)
        if keyword:
            sql += " AND ci.name ILIKE %s"; params.append(f"%{keyword}%")
        if authenticity_status:
            sql += " AND ci.authenticity_status=%s"; params.append(authenticity_status)
        elif not include_suspicious:
            sql += " AND ci.authenticity_status='verified'"
        else:
            sql += " AND ci.authenticity_status <> 'quarantined'"
        if regime_category:
            sql += " AND ci.regime_category=%s"; params.append(regime_category)
        sort_col = sort_by if sort_by in {"name", "entry_type", "mandatory", "country_code", "effective_date", "status", "updated_at"} else "updated_at"
        sort_expr = f"ci.{sort_col}"
        order = "ASC" if str(sort_order).lower() == "asc" else "DESC"
        with get_cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM ({sql}) t", params)
            total = int(cur.fetchone()["cnt"])
            cur.execute(f"{sql} ORDER BY {sort_expr} {order} NULLS LAST LIMIT %s OFFSET %s", params + [limit, offset])
            items = [dict(row) for row in cur.fetchall()]
        return {"total": total, "items": items}

    @staticmethod
    def get_by_compliance_id(compliance_id: str) -> Optional[Dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM compliance_index WHERE compliance_id=%s", (compliance_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_by_ids(record_ids: List[str], verified_only: bool = True) -> List[Dict]:
        if not record_ids:
            return []
        normalized_ids = [str(UUID(str(record_id))) for record_id in record_ids]
        sql = """
            SELECT compliance_id AS id, name, entry_type, country_code, regime_category
            FROM compliance_index
            WHERE compliance_id = ANY(%s::uuid[])
        """
        params: List[Any] = [normalized_ids]
        if verified_only:
            sql += " AND authenticity_status='verified'"
        with get_cursor() as cur:
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()]
        order = {record_id: index for index, record_id in enumerate(normalized_ids)}
        return sorted(rows, key=lambda row: order.get(str(row["id"]), 10**9))

    @staticmethod
    def list_by_country(country_code: str, verified_only: bool = True, limit: int = 5, include_inherited: bool = True) -> List[Dict]:
        sql = """
            SELECT compliance_id AS id, name, entry_type, country_code, regime_category
            FROM compliance_index
            WHERE country_code=%s
        """
        params: List[Any] = [country_code]
        if include_inherited:
            sql = """
                SELECT compliance_id AS id, name, entry_type, country_code, regime_category
                FROM compliance_index
                WHERE (
                    country_code = %s
                    OR country_code IN (
                        SELECT parent_code
                        FROM jurisdiction_inheritance
                        WHERE child_code = %s
                          AND enabled = TRUE
                          AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                    )
                )
            """
            params = [country_code, country_code]
        if verified_only:
            sql += " AND authenticity_status='verified'"
        else:
            sql += " AND authenticity_status <> 'quarantined'"
        sql += " ORDER BY updated_at DESC LIMIT %s"
        params.append(limit)
        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def list_by_product(
        product_code: str,
        country_code: Optional[str] = None,
        verified_only: bool = True,
        limit: int = 5,
        include_inherited: bool = True,
    ) -> List[Dict]:
        sql = """
            SELECT compliance_id AS id, name, entry_type, country_code, regime_category
            FROM compliance_index
            WHERE %s = ANY(applicable_products)
              AND regime_category=%s
        """
        params: List[Any] = [product_code, PRODUCT_REGIME_CATEGORY]
        if country_code:
            if include_inherited:
                sql += f" AND {_jurisdiction_scope_filter_sql('country_code')}"
                params.extend([country_code, country_code])
            else:
                sql += " AND country_code=%s"
                params.append(country_code)
        if verified_only:
            sql += " AND authenticity_status='verified'"
        else:
            sql += " AND authenticity_status <> 'quarantined'"
        sql += " ORDER BY updated_at DESC LIMIT %s"
        params.append(limit)
        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


class ComplianceLifecycleRepository:
    """Lifecycle milestone queries for staged legal/regulatory applicability."""

    @staticmethod
    def seed_key_regulation_milestones() -> Dict[str, Any]:
        """Idempotently refresh lifecycle countdown milestones for key regulations."""
        return {"cra": ComplianceLifecycleRepository.seed_cra_milestones()}

    @staticmethod
    def seed_cra_milestones() -> Dict[str, Any]:
        """Ensure EU CRA Article 71 staged applicability dates exist for alerts."""
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT ci.compliance_id::TEXT AS compliance_id
                FROM compliance_index ci
                WHERE ci.status = 'active'
                  AND ci.authenticity_status = 'verified'
                  AND ci.country_code = 'EU'
                  AND (
                    ci.official_url ILIKE '%eur-lex.europa.eu/eli/reg/2024/2847%'
                    OR ci.official_url ILIKE '%eur-lex.europa.eu/legal-content/%2024/2847%'
                    OR ci.name ILIKE '%Cyber Resilience Act%'
                    OR ci.name ILIKE '%2024/2847%'
                    OR ci.name ILIKE '%网络韧性法%'
                    OR ci.name ILIKE '%网络韧性法案%'
                  )
                ORDER BY
                  CASE
                    WHEN ci.official_url ILIKE '%eur-lex.europa.eu/eli/reg/2024/2847%' THEN 0
                    WHEN ci.official_url ILIKE '%2024/2847%' THEN 1
                    WHEN ci.name ILIKE '%Cyber Resilience Act%' THEN 2
                    ELSE 3
                  END,
                  ci.updated_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                return {
                    "status": "skipped",
                    "reason": "verified EU CRA record not found",
                    "milestones": 0,
                }

            compliance_id = row["compliance_id"]
            seeded_keys: List[str] = []
            for milestone in CRA_LIFECYCLE_MILESTONES:
                cur.execute(
                    """
                    INSERT INTO compliance_lifecycle_milestones (
                        compliance_id,
                        milestone_key,
                        milestone_type,
                        milestone_label_zh,
                        milestone_label_en,
                        milestone_date,
                        obligation_scope,
                        legal_basis,
                        source_note,
                        alertable,
                        priority
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (compliance_id, milestone_key)
                    DO UPDATE SET
                        milestone_type = EXCLUDED.milestone_type,
                        milestone_label_zh = EXCLUDED.milestone_label_zh,
                        milestone_label_en = EXCLUDED.milestone_label_en,
                        milestone_date = EXCLUDED.milestone_date,
                        obligation_scope = EXCLUDED.obligation_scope,
                        legal_basis = EXCLUDED.legal_basis,
                        source_note = EXCLUDED.source_note,
                        alertable = EXCLUDED.alertable,
                        priority = EXCLUDED.priority,
                        updated_at = NOW()
                    RETURNING milestone_key
                    """,
                    (
                        compliance_id,
                        milestone["milestone_key"],
                        milestone["milestone_type"],
                        milestone["milestone_label_zh"],
                        milestone["milestone_label_en"],
                        milestone["milestone_date"],
                        milestone["obligation_scope"],
                        milestone["legal_basis"],
                        milestone["source_note"],
                        milestone["alertable"],
                        milestone["priority"],
                    ),
                )
                returned = cur.fetchone()
                seeded_keys.append(returned["milestone_key"] if returned else milestone["milestone_key"])

            full_application_date = date(2027, 12, 11)
            cur.execute(
                """
                UPDATE compliance_knowledge
                SET effective_date = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (full_application_date, compliance_id),
            )
            cur.execute(
                """
                UPDATE compliance_index
                SET effective_date = %s,
                    updated_at = NOW()
                WHERE compliance_id = %s
                """,
                (full_application_date, compliance_id),
            )

        return {
            "status": "seeded",
            "compliance_id": compliance_id,
            "milestones": len(seeded_keys),
            "milestone_keys": seeded_keys,
            "full_application_date": full_application_date.isoformat(),
        }

    @staticmethod
    def get_upcoming_milestones(
        days: int = 30,
        country_code: Optional[str] = None,
        product_code: Optional[str] = None,
        entry_type: Optional[str] = None,
        mandatory: Optional[str] = None,
        keyword: Optional[str] = None,
        include_inherited: bool = False,
        mandatory_only: bool = False,
        limit: int = 200,
    ) -> List[Dict]:
        filters: List[str] = []
        params: List[Any] = [days]
        if country_code:
            if include_inherited:
                filters.append(_jurisdiction_scope_filter_sql("ci.country_code"))
                params.extend([country_code, country_code])
            else:
                filters.append("ci.country_code = %s")
                params.append(country_code)
        if product_code:
            filters.append("%s = ANY(ci.applicable_products)")
            params.append(product_code)
        if entry_type:
            filters.append("ci.entry_type = %s")
            params.append(entry_type)
        if mandatory:
            filters.append("ci.mandatory = %s")
            params.append(mandatory)
        if mandatory_only:
            filters.append("ci.mandatory = 'mandatory'")
        if keyword:
            filters.append("ci.name ILIKE %s")
            params.append(f"%{keyword}%")
        filter_sql = (" AND " + " AND ".join(filters)) if filters else ""
        params.append(limit)

        with get_cursor() as cur:
            cur.execute(
                f"""
                WITH lifecycle_milestones AS (
                    SELECT
                        lm.compliance_id,
                        lm.milestone_key,
                        lm.milestone_type,
                        lm.milestone_label_zh,
                        lm.milestone_label_en,
                        lm.milestone_date,
                        lm.obligation_scope,
                        lm.legal_basis,
                        lm.source_note,
                        lm.priority,
                        lm.alertable
                    FROM compliance_lifecycle_milestones lm
                    WHERE lm.alertable = TRUE
                    UNION ALL
                    SELECT
                        ci_fallback.compliance_id,
                        'primary_effective_date'::varchar AS milestone_key,
                        'application'::varchar AS milestone_type,
                        '主要生效/适用日期'::text AS milestone_label_zh,
                        'Primary effective/application date'::text AS milestone_label_en,
                        ci_fallback.effective_date AS milestone_date,
                        NULL::text AS obligation_scope,
                        NULL::text AS legal_basis,
                        'Fallback from compliance_index.effective_date because no lifecycle milestones are stored.'::text AS source_note,
                        999 AS priority,
                        TRUE AS alertable
                    FROM compliance_index ci_fallback
                    WHERE ci_fallback.effective_date IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1
                          FROM compliance_lifecycle_milestones lm_existing
                          WHERE lm_existing.compliance_id = ci_fallback.compliance_id
                            AND lm_existing.alertable = TRUE
                      )
                )
                SELECT
                    ci.compliance_id AS id,
                    ci.name,
                    ci.entry_type,
                    ci.country_code,
                    c.name_zh AS country_name,
                    c.priority,
                    ci.mandatory,
                    ci.applicable_products,
                    ci.official_url,
                    ci.summary,
                    lm.milestone_key,
                    lm.milestone_type,
                    lm.milestone_label_zh,
                    lm.milestone_label_en,
                    lm.milestone_date,
                    lm.milestone_date AS effective_date,
                    lm.milestone_date - CURRENT_DATE AS days_until_milestone,
                    lm.milestone_date - CURRENT_DATE AS days_until_effective,
                    lm.obligation_scope,
                    lm.legal_basis,
                    lm.source_note
                FROM compliance_index ci
                JOIN lifecycle_milestones lm ON lm.compliance_id = ci.compliance_id
                JOIN countries c ON c.code = ci.country_code
                WHERE ci.status='active'
                  AND ci.authenticity_status='verified'
                  AND milestone_date >= CURRENT_DATE
                  AND milestone_date <= CURRENT_DATE + (%s * INTERVAL '1 day')
                  {filter_sql}
                ORDER BY milestone_date ASC, lm.priority ASC, c.priority, ci.name
                LIMIT %s
                """,
                params,
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def get_milestones_for_date(target_date: date, mandatory_only: bool = True) -> List[Dict]:
        filters = ["lm.milestone_date = %s"]
        params: List[Any] = [target_date]
        if mandatory_only:
            filters.append("ci.mandatory = 'mandatory'")
        filter_sql = " AND ".join(filters)
        with get_cursor() as cur:
            cur.execute(
                f"""
                WITH lifecycle_milestones AS (
                    SELECT
                        lm.compliance_id,
                        lm.milestone_key,
                        lm.milestone_type,
                        lm.milestone_label_zh,
                        lm.milestone_label_en,
                        lm.milestone_date,
                        lm.obligation_scope,
                        lm.legal_basis,
                        lm.source_note,
                        lm.priority
                    FROM compliance_lifecycle_milestones lm
                    WHERE lm.alertable = TRUE
                    UNION ALL
                    SELECT
                        ci_fallback.compliance_id,
                        'primary_effective_date'::varchar,
                        'application'::varchar,
                        '主要生效/适用日期'::text,
                        'Primary effective/application date'::text,
                        ci_fallback.effective_date,
                        NULL::text,
                        NULL::text,
                        'Fallback from compliance_index.effective_date because no lifecycle milestones are stored.'::text,
                        999
                    FROM compliance_index ci_fallback
                    WHERE ci_fallback.effective_date IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1
                          FROM compliance_lifecycle_milestones lm_existing
                          WHERE lm_existing.compliance_id = ci_fallback.compliance_id
                            AND lm_existing.alertable = TRUE
                      )
                )
                SELECT
                    ci.compliance_id AS id,
                    ci.name,
                    ci.country_code,
                    c.name_zh AS country_name,
                    c.priority,
                    ci.mandatory,
                    ci.applicable_products,
                    ci.official_url,
                    lm.milestone_key,
                    lm.milestone_type,
                    lm.milestone_label_zh,
                    lm.milestone_label_en,
                    lm.milestone_date AS effective_date,
                    lm.milestone_date - CURRENT_DATE AS days_until_effective,
                    lm.obligation_scope,
                    lm.legal_basis,
                    lm.source_note
                FROM compliance_index ci
                JOIN lifecycle_milestones lm ON lm.compliance_id = ci.compliance_id
                JOIN countries c ON c.code = ci.country_code
                WHERE ci.status = 'active'
                  AND ci.authenticity_status = 'verified'
                  AND {filter_sql}
                ORDER BY c.priority, lm.priority, ci.name
                """,
                params,
            )
            return [dict(row) for row in cur.fetchall()]

class AgentCaseRepository:
    """agent_cases 表的数据访问层。"""

    @staticmethod
    def create(case: Dict[str, Any]) -> str:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_cases
                        (question, country_code, product_code, document_id, intent, status,
                         failure_reason, evidence_snapshot, tool_trace, suggested_actions,
                         source, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        case["question"],
                        case.get("country_code"),
                        case.get("product_code"),
                        case.get("document_id"),
                        case["intent"],
                        case.get("status") or "open",
                        case.get("failure_reason"),
                        json.dumps(case.get("evidence_snapshot") or {}, ensure_ascii=False),
                        json.dumps(case.get("tool_trace") or [], ensure_ascii=False),
                        case.get("suggested_actions") or [],
                        case.get("source") or "agent",
                        case.get("created_by") or "agent",
                    ),
                )
                return str(cur.fetchone()[0])

    @staticmethod
    def list_filtered(
        status: Optional[str] = None,
        country_code: Optional[str] = None,
        intent: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        sql = "SELECT * FROM agent_cases WHERE 1=1"
        params: List[Any] = []
        if status:
            sql += " AND status=%s"
            params.append(status)
        if country_code:
            sql += " AND country_code=%s"
            params.append(country_code)
        if intent:
            sql += " AND intent=%s"
            params.append(intent)
        with get_cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM ({sql}) t", params)
            total = int(cur.fetchone()["cnt"])
            cur.execute(f"{sql} ORDER BY created_at DESC LIMIT %s OFFSET %s", params + [limit, offset])
            return {"total": total, "items": [dict(row) for row in cur.fetchall()]}

    @staticmethod
    def apply_decision(case_id: str, decision: Dict[str, Any]) -> Dict[str, Any]:
        updates = ["status=%s", "updated_at=NOW()"]
        params: List[Any] = [decision["status"]]
        for field in (
            "handler_note",
            "linked_source_record_id",
            "linked_review_case_id",
            "linked_document_id",
            "handled_by",
        ):
            if field in decision:
                updates.append(f"{field}=%s")
                params.append(decision.get(field))
        params.append(case_id)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE agent_cases
                    SET {', '.join(updates)}
                    WHERE id=%s
                    RETURNING *
                    """,
                    params,
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError("agent case 不存在")
                return dict(row)


# ============================================================
# 工具函数
# ============================================================

def _verified_document_filter_sql(document_column: str) -> str:
    return f"""
        (
            EXISTS (
                SELECT 1
                FROM compliance_index ci
                JOIN regulation_documents d ON d.id = {document_column}
                WHERE (
                    ci.document_id = {document_column}
                    OR d.compliance_id = ci.compliance_id
                  )
                  AND ci.status = 'active'
                  AND ci.authenticity_status = 'verified'
            )
            OR EXISTS (
                SELECT 1
                FROM canonical_requirements cr
                WHERE cr.document_id = {document_column}
                  AND cr.verification_status = 'verified'
            )
        )
    """


def _document_regime_filter_sql(document_column: str) -> str:
    return f"""
        EXISTS (
            SELECT 1
            FROM compliance_index ci_regime
            JOIN regulation_documents d_regime ON d_regime.id = {document_column}
            WHERE (
                ci_regime.document_id = {document_column}
                OR d_regime.compliance_id = ci_regime.compliance_id
              )
              AND ci_regime.status = 'active'
              AND ci_regime.authenticity_status = 'verified'
              AND ci_regime.regime_category = %s
        )
    """


def _jurisdiction_scope_filter_sql(country_column: str) -> str:
    return f"""
        (
            {country_column} = %s
            OR {country_column} IN (
                SELECT ji.parent_code
                FROM jurisdiction_inheritance ji
                WHERE ji.child_code = %s
                  AND ji.enabled = TRUE
                  AND (ji.effective_to IS NULL OR ji.effective_to >= CURRENT_DATE)
            )
        )
    """


def _normalize_arrays(data: Dict[str, Any]) -> None:
    """将 Python list 转换为 psycopg2 可接受的格式"""
    array_fields = [
        "technical_standards", "regulation_basis",
        "applicable_products", "testing_bodies", "changed_fields",
        "source_chunk_ids",
    ]
    for field in array_fields:
        if field in data and isinstance(data[field], list):
            pass  # psycopg2 自动处理 Python list → PostgreSQL array


def _normalize_jsonb(data: Dict[str, Any], fields: List[str]) -> None:
    """将 dict 字段序列化为 JSON 字符串"""
    for field in fields:
        if field in data and isinstance(data[field], (dict, list)):
            data[field] = json.dumps(data[field], ensure_ascii=False)


def _extract_query_section_refs(question: str) -> List[str]:
    refs: List[str] = []
    patterns = [
        r"(?i)article\s+\d+[a-z\-]*",
        r"(?i)chapter\s+[ivxlcdm]+",
        r"(?i)section\s+\d+",
        r"(?i)annex\s+[a-z0-9]+",
        r"第[一二三四五六七八九十百千0-9]+[章节条]",
        r"附件[一二三四五六七八九十0-9A-Za-z]+",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, question):
            normalized = " ".join(str(match).strip().split())
            if normalized.lower() not in [ref.lower() for ref in refs]:
                refs.append(normalized)
    return refs


def compute_diff(
    old: Dict[str, Any],
    new: Dict[str, Any],
    ignore_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    比较两个字典，返回差异信息。
    返回格式: {"changed_fields": [...], "diff": {field: {"old": x, "new": y}}}
    """
    ignore = set(ignore_fields or ["id", "updated_at", "last_checked", "version", "created_at", "priority", "country_name", "score", "days_until_effective"])
    changed_fields = []
    diff: Dict[str, Any] = {}

    for key in set(list(old.keys()) + list(new.keys())):
        if key in ignore:
            continue
        old_val = old.get(key)
        new_val = new.get(key)
        if _values_differ(old_val, new_val):
            changed_fields.append(key)
            diff[key] = {"old": old_val, "new": new_val}

    return {"changed_fields": changed_fields, "diff": diff}


def _values_differ(a: Any, b: Any) -> bool:
    """比较两个值是否有实质差异（处理 None、列表、JSON 等）"""
    if a is None and b is None:
        return False
    if type(a) != type(b):
        # 空列表和 None 视为相同
        if (a is None and b == []) or (a == [] and b is None):
            return False
        return True
    if isinstance(a, (list, tuple)):
        return sorted(str(x) for x in a) != sorted(str(x) for x in b)
    if isinstance(a, dict):
        return json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)
    return str(a) != str(b)
