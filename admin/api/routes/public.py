"""
admin/api/routes/public.py
公开查询接口 - 无需登录，供大屏展示使用
"""
from __future__ import annotations
import logging
from fastapi import APIRouter
from database.connection import get_cursor
from collector.translation.repository import list_translations_for_entities
from collector.translation.service import attach_translation_fields

router = APIRouter()
logger = logging.getLogger(__name__)


def _date_str(value) -> str | None:
    if value is None:
        return None
    return str(value)[:10]


def _datetime_str(value) -> str | None:
    if value is None:
        return None
    return str(value)[:16]


def _normalize_country(row: dict) -> dict:
    if row.get("code") == "TW":
        row["name_zh"] = "中国台湾"
        row["name_en"] = "Taiwan, China"
        row["jurisdiction_type"] = row.get("jurisdiction_type") or "special_region"
    elif row.get("code") == "EU":
        row["jurisdiction_type"] = row.get("jurisdiction_type") or "regional_bloc"
    else:
        row["jurisdiction_type"] = row.get("jurisdiction_type") or "country"
    return row


def _translation_map(entity_type: str, entity_ids: list[str]) -> dict[tuple[str, str], str]:
    try:
        return list_translations_for_entities(entity_type, entity_ids)
    except Exception as exc:
        # Translation is an additive display layer. API data should still work
        # during first deployment before the translation migration/batch finishes.
        logger.warning("translation lookup skipped [%s]: %s", entity_type, exc)
        return {}


@router.get("/stats")
async def get_global_stats():
    """全局统计数据。

    大屏必须跟国家覆盖矩阵同源，而不是只看 verified 记录。
    """
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                COALESCE(SUM(csc.verified_record_count), 0) AS total,
                COUNT(*) FILTER (
                    WHERE COALESCE(csc.coverage_status, 'needs_source_research') <> 'needs_source_research'
                ) AS countries,
                COALESCE(SUM(csc.verified_record_count) FILTER (
                    WHERE csc.coverage_status = 'verified_records_available'
                ), 0) AS verified_records,
                COUNT(*) FILTER (
                    WHERE csc.coverage_status = 'official_sources_seeded'
                ) AS official_source_countries,
                COUNT(*) FILTER (
                    WHERE csc.coverage_status = 'researched_no_specific_source'
                ) AS no_specific_source_countries,
                COALESCE(SUM(csc.official_source_count), 0) AS official_sources,
                COALESCE(SUM(csc.product_verified_count), 0) AS product_verified,
                COALESCE(SUM(csc.verified_record_count) FILTER (
                    WHERE csc.product_coverage_status = 'product_regime_verified'
                ), 0) AS product_regime_records
            FROM countries c
            LEFT JOIN country_source_coverage csc ON csc.country_code = c.code
            WHERE c.enabled = TRUE
        """)
        summary = dict(cur.fetchone())
        cur.execute("""
            SELECT
                csc.country_code,
                c.name_zh AS country_name,
                csc.coverage_status,
                csc.product_coverage_status,
                csc.verified_record_count,
                csc.official_source_count,
                GREATEST(
                    COALESCE(csc.verified_record_count, 0),
                    COALESCE(csc.official_source_count, 0)
                ) AS cnt
            FROM country_source_coverage csc
            JOIN countries c ON c.code = csc.country_code
            WHERE c.enabled = TRUE
              AND csc.coverage_status <> 'needs_source_research'
            ORDER BY
                csc.verified_record_count DESC,
                csc.official_source_count DESC,
                c.priority
            LIMIT 10
        """)
        top = [dict(r) for r in cur.fetchall()]
    return {
        **summary,
        "mandatory": summary.get("product_verified", 0),
        "certifications": summary.get("official_sources", 0),
        "top_countries": top,
    }


@router.get("/countries")
async def get_all_countries():
    """获取所有国家覆盖状态。

    这里不再 INNER JOIN verified 记录，否则“已找到官方源但未闭环”的国家不会进入大屏。
    """
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                c.code,
                c.name_zh,
                c.name_en,
                c.region,
                c.jurisdiction_type,
                c.priority,
                COALESCE(csc.coverage_status, 'needs_source_research') AS coverage_status,
                COALESCE(csc.product_coverage_status, 'pending_source_research') AS product_coverage_status,
                COALESCE(csc.official_source_count, 0) AS official_source_count,
                COALESCE(csc.source_record_count, 0) AS source_record_count,
                COALESCE(csc.verified_record_count, 0) AS total,
                COALESCE(csc.verified_record_count, 0) AS verified_record_count,
                COALESCE(inherited.inherited_verified_count, 0) AS inherited_verified_count,
                COALESCE(csc.verified_record_count, 0) + COALESCE(inherited.inherited_verified_count, 0) AS display_verified_count,
                COALESCE(csc.product_verified_count, 0) AS product_verified_count,
                COALESCE(csc.general_verified_count, 0) AS general_verified_count,
                COALESCE(csc.suspicious_record_count, 0) AS suspicious_record_count,
                COALESCE(csc.quarantined_record_count, 0) AS quarantined_record_count,
                csc.review_note,
                csc.next_action,
                csc.last_checked_at,
                COALESCE(v.mandatory_cnt, 0) AS mandatory_cnt,
                COALESCE(v.cert_cnt, 0) AS cert_cnt
            FROM countries c
            LEFT JOIN country_source_coverage csc ON csc.country_code = c.code
            LEFT JOIN (
                SELECT
                    country_code,
                    COUNT(*) FILTER (WHERE mandatory='mandatory') AS mandatory_cnt,
                    COUNT(*) FILTER (WHERE entry_type='certification') AS cert_cnt
                FROM compliance_index
                WHERE status='active' AND authenticity_status='verified'
                    GROUP BY country_code
            ) v ON v.country_code = c.code
            LEFT JOIN (
                SELECT
                    ji.child_code AS country_code,
                    COUNT(*) AS inherited_verified_count
                FROM jurisdiction_inheritance ji
                JOIN compliance_index ci ON ci.country_code = ji.parent_code
                WHERE ji.enabled = TRUE
                  AND (ji.effective_to IS NULL OR ji.effective_to >= CURRENT_DATE)
                  AND ci.status='active'
                  AND ci.authenticity_status='verified'
                GROUP BY ji.child_code
            ) inherited ON inherited.country_code = c.code
            WHERE c.enabled = TRUE
            ORDER BY
                CASE COALESCE(csc.coverage_status, 'needs_source_research')
                    WHEN 'verified_records_available' THEN 0
                    WHEN 'official_sources_seeded' THEN 1
                    WHEN 'researched_no_specific_source' THEN 2
                    ELSE 3
                END,
                COALESCE(csc.verified_record_count, 0) DESC,
                COALESCE(csc.official_source_count, 0) DESC,
                c.priority,
                c.code
        """)
        rows = [dict(r) for r in cur.fetchall()]
        coverage_translations = _translation_map(
            "country_source_coverage",
            [str(r.get("code")) for r in rows],
        )
        for r in rows:
            _normalize_country(r)
            if r.get("last_checked_at"):
                r["last_checked_at"] = _datetime_str(r["last_checked_at"])
            for internal_key in ("source_record_count", "suspicious_record_count", "quarantined_record_count"):
                r.pop(internal_key, None)
            enriched = attach_translation_fields(
                {"country_code": r["code"], **r},
                coverage_translations,
                entity_id_field="country_code",
            )
            r.update(enriched)
        return rows


@router.get("/country/{code}")
async def get_country_detail(code: str):
    """获取指定国家的合规详情"""
    code = code.upper()
    with get_cursor() as cur:
        # 国家基本信息
        cur.execute("SELECT * FROM countries WHERE code=%s", (code,))
        country = cur.fetchone()
        if not country:
            return {"error": "国家不存在"}
        country = _normalize_country(dict(country))

        cur.execute("""
            SELECT *
            FROM country_source_coverage
            WHERE country_code=%s
        """, (code,))
        coverage = cur.fetchone()
        coverage = dict(coverage) if coverage else {
            "country_code": code,
            "coverage_status": "needs_source_research",
            "product_coverage_status": "pending_source_research",
            "official_source_count": 0,
            "source_record_count": 0,
            "verified_record_count": 0,
            "product_verified_count": 0,
            "general_verified_count": 0,
            "review_note": "尚未形成覆盖矩阵记录",
            "next_action": "刷新国家覆盖矩阵",
        }
        for key in ("last_checked_at", "updated_at"):
            if coverage.get(key):
                coverage[key] = _datetime_str(coverage[key])
        coverage = attach_translation_fields(
            coverage,
            _translation_map("country_source_coverage", [code]),
            entity_id_field="country_code",
        )

        # 合规条目
        cur.execute("""
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
            SELECT
                   ci.compliance_id AS id,
                   ci.name,
                   ci.entry_type,
                   ci.regime_category,
                   ci.mandatory,
                   ci.effective_date,
                   ci.published_date,
                   ci.issuing_body,
                   ci.official_url,
                   ci.status,
                   ci.summary,
                   ci.applicable_products,
                   COALESCE(ready_doc.id, ci.document_id) AS document_id,
                   ci.source_artifact_id,
                   ci.source_record_id,
                   ci.updated_at,
                   ci.country_code AS source_jurisdiction_code,
                   source_country.name_zh AS source_jurisdiction_name,
                   js.scope_origin,
                   js.inherited_from_code,
                   js.inheritance_reason
            FROM compliance_index ci
            JOIN jurisdiction_scope js ON js.source_code = ci.country_code
            JOIN countries source_country ON source_country.code = ci.country_code
            LEFT JOIN LATERAL (
                SELECT d.id
                FROM regulation_documents d
                WHERE d.compliance_id = ci.compliance_id
                  AND d.index_status = 'ready'
                  AND COALESCE(d.chunk_count, 0) > 0
                ORDER BY d.created_at DESC
                LIMIT 1
            ) ready_doc ON TRUE
            WHERE ci.status='active'
              AND ci.authenticity_status='verified'
            ORDER BY
                CASE js.scope_origin WHEN 'local' THEN 0 ELSE 1 END,
                CASE ci.regime_category WHEN 'product_regime' THEN 0 ELSE 1 END,
                mandatory DESC,
                entry_type,
                name
        """, (code, code))
        items = []
        for r in cur.fetchall():
            row = dict(r)
            row["effective_date"] = _date_str(row.get("effective_date"))
            row["published_date"] = _date_str(row.get("published_date"))
            row["updated_at"] = _datetime_str(row.get("updated_at"))
            items.append(row)
        item_translations = _translation_map(
            "compliance_index",
            [str(item.get("id")) for item in items],
        )
        items = [
            attach_translation_fields(item, item_translations, entity_id_field="id")
            for item in items
        ]

        cur.execute("""
            WITH jurisdiction_scope AS (
                SELECT %s::varchar AS source_code, 'local'::text AS scope_origin
                UNION ALL
                SELECT ji.parent_code AS source_code, 'inherited'::text AS scope_origin
                FROM jurisdiction_inheritance ji
                WHERE ji.child_code = %s
                  AND ji.enabled = TRUE
                  AND (ji.effective_to IS NULL OR ji.effective_to >= CURRENT_DATE)
            )
            SELECT
                os.id,
                os.name,
                os.source_type,
                os.list_url,
                os.base_url,
                os.allowed_domains,
                os.entry_type_scope,
                os.priority,
                os.last_checked_at,
                os.last_success_at,
                os.last_error,
                os.parser_config,
                os.country_code AS source_jurisdiction_code,
                js.scope_origin
            FROM official_sources os
            JOIN jurisdiction_scope js ON js.source_code = os.country_code
            WHERE os.enabled = TRUE
            ORDER BY CASE js.scope_origin WHEN 'local' THEN 0 ELSE 1 END, os.priority, os.name
            LIMIT 20
        """, (code, code))
        official_sources = []
        for r in cur.fetchall():
            row = dict(r)
            parser_config = row.get("parser_config") or {}
            row["official_evidence_url"] = parser_config.get("official_evidence_url") or row.get("list_url")
            row["evidence_note"] = parser_config.get("evidence_note")
            row["last_checked_at"] = _datetime_str(row.get("last_checked_at"))
            row["last_success_at"] = _datetime_str(row.get("last_success_at"))
            row.pop("parser_config", None)
            official_sources.append(row)
        source_translations = _translation_map(
            "official_sources",
            [str(source.get("id")) for source in official_sources],
        )
        official_sources = [
            attach_translation_fields(source, source_translations, entity_id_field="id")
            for source in official_sources
        ]

        # 即将进入下一适用阶段。使用 lifecycle milestones，避免把“已生效”
        # 和“全面适用/报告义务开始适用”等节点混成一个日期。
        cur.execute("""
            WITH jurisdiction_scope AS (
                SELECT %s::varchar AS source_code, 'local'::text AS scope_origin
                UNION ALL
                SELECT ji.parent_code AS source_code, 'inherited'::text AS scope_origin
                FROM jurisdiction_inheritance ji
                WHERE ji.child_code = %s
                  AND ji.enabled = TRUE
                  AND (ji.effective_to IS NULL OR ji.effective_to >= CURRENT_DATE)
            ),
            lifecycle_milestones AS (
                SELECT
                    lm.compliance_id,
                    lm.milestone_key,
                    lm.milestone_type,
                    lm.milestone_label_zh,
                    lm.milestone_label_en,
                    lm.milestone_date,
                    lm.obligation_scope,
                    lm.legal_basis,
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
                ci.country_code AS source_jurisdiction_code,
                js.scope_origin
            FROM compliance_index ci
            JOIN jurisdiction_scope js ON js.source_code = ci.country_code
            JOIN lifecycle_milestones lm ON lm.compliance_id = ci.compliance_id
            WHERE ci.status='active' AND ci.authenticity_status='verified'
              AND lm.milestone_date >= CURRENT_DATE
              AND lm.milestone_date <= CURRENT_DATE + INTERVAL '90 days'
            ORDER BY lm.milestone_date, lm.priority, ci.name
            LIMIT 20
        """, (code, code))
        upcoming = []
        for r in cur.fetchall():
            row = dict(r)
            row["effective_date"] = _date_str(row.get("effective_date"))
            row["milestone_date"] = _date_str(row.get("milestone_date"))
            row["days_left"] = row.get("days_until_milestone") or row.get("days_until_effective")
            upcoming.append(row)
        upcoming_translations = _translation_map(
            "compliance_index",
            [str(item.get("id")) for item in upcoming],
        )
        upcoming = [
            attach_translation_fields(item, upcoming_translations, entity_id_field="id")
            for item in upcoming
        ]

        # 最新变更：legacy change_log 不覆盖新证据链写入的 verified 记录，
        # 所以同时纳入审核 verified 时间作为大屏动态来源。
        cur.execute("""
            WITH events AS (
                SELECT ci.compliance_id AS record_id,
                       cl.change_type::text AS change_type,
                       cl.changed_at,
                       ci.name,
                       0 AS source_rank
                FROM change_log cl
                JOIN compliance_index ci ON cl.record_id = ci.compliance_id
                WHERE ci.country_code=%s
                  AND ci.status='active'
                  AND ci.authenticity_status='verified'
                UNION ALL
                SELECT ci.compliance_id AS record_id,
                       'created' AS change_type,
                       COALESCE(rc.checked_at, ci.updated_at) AS changed_at,
                       ci.name,
                       1 AS source_rank
                FROM compliance_index ci
                LEFT JOIN review_cases rc ON rc.id = ci.review_case_id
                WHERE ci.country_code=%s
                  AND ci.status='active'
                  AND ci.authenticity_status='verified'
            )
            SELECT record_id AS id, change_type, changed_at, name
            FROM (
                SELECT DISTINCT ON (record_id)
                       record_id, change_type, changed_at, name
                FROM events
                WHERE changed_at IS NOT NULL
                ORDER BY record_id, changed_at DESC, source_rank
            ) latest
            ORDER BY changed_at DESC
            LIMIT 5
        """, (code, code))
        changes = []
        for r in cur.fetchall():
            row = dict(r)
            row["changed_at"] = _datetime_str(row.get("changed_at"))
            changes.append(row)
        change_translations = _translation_map(
            "compliance_index",
            [str(item.get("id")) for item in changes],
        )
        changes = [
            attach_translation_fields(item, change_translations, entity_id_field="id")
            for item in changes
        ]

    return {
        "country": country,
        "coverage": coverage,
        "items": items,
        "official_sources": official_sources,
        "upcoming": upcoming,
        "changes": changes,
        "summary": {
            "total": len(items),
            "mandatory": len([i for i in items if i["mandatory"] == "mandatory"]),
            "voluntary": len([i for i in items if i["mandatory"] != "mandatory"]),
            "certifications": len([i for i in items if i["entry_type"] == "certification"]),
            "regulations": len([i for i in items if i["entry_type"] == "regulation"]),
            "product_regime": len([i for i in items if i.get("regime_category") == "product_regime"]),
            "general_cyber_law": len([i for i in items if i.get("regime_category") == "general_cyber_law"]),
            "official_sources": len(official_sources),
            "coverage_status": coverage.get("coverage_status"),
            "product_coverage_status": coverage.get("product_coverage_status"),
        }
    }


@router.get("/item/{record_id}")
async def get_public_item_detail(record_id: str):
    """大屏公开条目详情。只暴露 verified 读模型记录，避免候选/可疑项进入展示。"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                ci.compliance_id AS id,
                ci.name,
                ci.country_code,
                c.name_zh AS country_name,
                c.name_en AS country_name_en,
                c.region,
                ci.entry_type,
                ci.regime_category,
                ci.mandatory,
                ci.status,
                ci.issuing_body,
                ci.official_url,
                ci.applicable_products,
                ci.effective_date,
                ci.published_date,
                ci.summary,
                COALESCE(ready_doc.id, ci.document_id) AS document_id,
                ci.source_artifact_id,
                ci.review_case_id,
                ci.updated_at,
                rc.evidence_note,
                rc.reasons,
                rc.checked_at,
                COALESCE(sa.artifact_url, sa.official_url) AS source_artifact_url,
                sa.artifact_sha256
            FROM compliance_index ci
            JOIN countries c ON c.code = ci.country_code
            LEFT JOIN review_cases rc ON rc.id = ci.review_case_id
            LEFT JOIN source_artifacts sa ON sa.id = ci.source_artifact_id
            LEFT JOIN LATERAL (
                SELECT d.id
                FROM regulation_documents d
                WHERE d.compliance_id = ci.compliance_id
                  AND d.index_status = 'ready'
                  AND COALESCE(d.chunk_count, 0) > 0
                ORDER BY d.created_at DESC
                LIMIT 1
            ) ready_doc ON TRUE
            WHERE ci.compliance_id=%s
              AND ci.status='active'
              AND ci.authenticity_status='verified'
            LIMIT 1
        """, (record_id,))
        row = cur.fetchone()
        if not row:
            return {"error": "记录不存在"}
        item = dict(row)
        for key in ("effective_date", "published_date"):
            item[key] = _date_str(item.get(key))
        for key in ("updated_at", "checked_at"):
            item[key] = _datetime_str(item.get(key))
        if item.get("country_code") == "TW":
            item["country_name"] = "中国台湾"
            item["country_name_en"] = "Taiwan, China"
        item_translations = {}
        item_translations.update(_translation_map("compliance_index", [str(item["id"])]))
        item = attach_translation_fields(item, item_translations, entity_id_field="id")
        cur.execute("""
            WITH lifecycle_milestones AS (
                SELECT
                    lm.milestone_key,
                    lm.milestone_type,
                    lm.milestone_label_zh,
                    lm.milestone_label_en,
                    lm.milestone_date,
                    lm.obligation_scope,
                    lm.legal_basis,
                    lm.source_note,
                    lm.alertable,
                    lm.priority
                FROM compliance_lifecycle_milestones lm
                WHERE lm.compliance_id = %s
                UNION ALL
                SELECT
                    'primary_effective_date'::varchar,
                    'application'::varchar,
                    '主要生效/适用日期'::text,
                    'Primary effective/application date'::text,
                    ci.effective_date,
                    NULL::text,
                    NULL::text,
                    'Fallback from compliance_index.effective_date because no lifecycle milestones are stored.'::text,
                    TRUE,
                    999
                FROM compliance_index ci
                WHERE ci.compliance_id = %s
                  AND ci.effective_date IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM compliance_lifecycle_milestones lm_existing
                      WHERE lm_existing.compliance_id = ci.compliance_id
                  )
            )
            SELECT *
            FROM lifecycle_milestones
            ORDER BY priority, milestone_date
        """, (record_id, record_id))
        milestones = []
        for milestone in cur.fetchall():
            milestone_row = dict(milestone)
            milestone_row["milestone_date"] = _date_str(milestone_row.get("milestone_date"))
            milestones.append(milestone_row)
        item["lifecycle_milestones"] = milestones
        if item.get("review_case_id"):
            review_translations = _translation_map("review_cases", [str(item["review_case_id"])])
            if review_translations:
                translations = dict(item.get("translations") or {})
                for (_, field_name), translated_text in review_translations.items():
                    translations[field_name] = translated_text
                    if field_name.replace("_", "").isalnum() and "[" not in field_name and "." not in field_name:
                        item[f"{field_name}_zh"] = translated_text
                item["translations"] = translations
        return item


@router.get("/recent-changes")
async def get_recent_changes():
    """最近变更动态（大屏滚动展示）"""
    with get_cursor() as cur:
        cur.execute("""
            WITH events AS (
                SELECT ci.compliance_id AS record_id,
                       cl.change_type::text AS change_type,
                       cl.changed_at,
                       ci.name,
                       ci.country_code,
                       c.name_zh AS country_name,
                       0 AS source_rank
                FROM change_log cl
                JOIN compliance_index ci ON cl.record_id = ci.compliance_id
                JOIN countries c ON ci.country_code = c.code
                WHERE ci.status='active'
                  AND ci.authenticity_status='verified'
                UNION ALL
                SELECT ci.compliance_id AS record_id,
                       'created' AS change_type,
                       COALESCE(rc.checked_at, ci.updated_at) AS changed_at,
                       ci.name,
                       ci.country_code,
                       c.name_zh AS country_name,
                       1 AS source_rank
                FROM compliance_index ci
                JOIN countries c ON ci.country_code = c.code
                LEFT JOIN review_cases rc ON rc.id = ci.review_case_id
                WHERE ci.status='active'
                  AND ci.authenticity_status='verified'
            )
            SELECT record_id AS id, change_type, changed_at, name, country_code, country_name
            FROM (
                SELECT DISTINCT ON (record_id)
                       record_id, change_type, changed_at, name, country_code, country_name
                FROM events
                WHERE changed_at IS NOT NULL
                ORDER BY record_id, changed_at DESC, source_rank
            ) latest
            ORDER BY changed_at DESC
            LIMIT 20
        """)
        items = []
        for r in cur.fetchall():
            row = dict(r)
            if row.get("changed_at"): row["changed_at"] = str(row["changed_at"])[:16]
            items.append(row)
        translations = _translation_map(
            "compliance_index",
            [str(item.get("id")) for item in items],
        )
        items = [
            attach_translation_fields(item, translations, entity_id_field="id")
            for item in items
        ]
    return {"items": items}
