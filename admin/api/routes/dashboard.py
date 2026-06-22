"""
admin/api/routes/dashboard.py
仪表盘统计数据接口
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from admin.api.auth import require_admin_user
from database.connection import get_cursor
from database.repository import ComplianceLifecycleRepository

router = APIRouter()
ALLOWED_UPCOMING_DAYS = {30, 90, 180, 360}


def _validate_upcoming_days(days: int) -> int:
    if days not in ALLOWED_UPCOMING_DAYS:
        raise HTTPException(status_code=400, detail="days 仅支持 30/90/180/360")
    return days


def _scalar(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return 0
    return int(row.get("cnt") or 0)


def _stage_health(primary: int, blockers: int = 0) -> str:
    if blockers > 0:
        return "attention"
    if primary > 0:
        return "ready"
    return "empty"


@router.get("/workflow")
async def get_workflow(current_user: str = Depends(require_admin_user)):
    """产品主流程状态：采集 -> 核验 -> 知识库 -> 规格 -> 查询 -> 周报。"""
    with get_cursor() as cur:
        source_candidates = _scalar(
            cur,
            "SELECT COUNT(*) AS cnt FROM source_records WHERE source_status='candidate'",
        )
        artifacts_downloaded = _scalar(
            cur,
            "SELECT COUNT(*) AS cnt FROM source_artifacts WHERE download_status='downloaded'",
        )
        artifacts_failed = _scalar(
            cur,
            "SELECT COUNT(*) AS cnt FROM source_artifacts WHERE download_status='failed'",
        )
        review_verified = _scalar(
            cur,
            "SELECT COUNT(*) AS cnt FROM review_cases WHERE current_status='verified'",
        )
        review_suspicious = _scalar(
            cur,
            "SELECT COUNT(*) AS cnt FROM review_cases WHERE current_status='suspicious'",
        )
        review_quarantined = _scalar(
            cur,
            "SELECT COUNT(*) AS cnt FROM review_cases WHERE current_status='quarantined'",
        )
        verified_records = _scalar(
            cur,
            """
            SELECT COUNT(*) AS cnt
            FROM compliance_index
            WHERE status='active' AND authenticity_status='verified'
            """,
        )
        ready_documents = _scalar(
            cur,
            "SELECT COUNT(*) AS cnt FROM regulation_documents WHERE index_status='ready'",
        )
        parsed_documents = _scalar(
            cur,
            "SELECT COUNT(*) AS cnt FROM regulation_documents WHERE parse_status='done'",
        )
        chunks = _scalar(cur, "SELECT COUNT(*) AS cnt FROM regulation_document_chunks")
        spec_requirements = _scalar(cur, "SELECT COUNT(*) AS cnt FROM regulation_spec_requirements")
        docs_with_specs = _scalar(
            cur,
            """
            SELECT COUNT(*) AS cnt
            FROM regulation_documents
            WHERE COALESCE(spec_requirement_count, 0) > 0
            """,
        )
        pending_changes = _scalar(
            cur,
            """
            SELECT COUNT(*) AS cnt
            FROM change_log cl
            JOIN compliance_index ci ON cl.record_id = ci.compliance_id
            WHERE cl.reviewed=FALSE
              AND ci.status='active'
              AND ci.authenticity_status='verified'
            """,
        )
        weekly_reports = _scalar(
            cur,
            """
            SELECT COUNT(*) AS cnt
            FROM report_records
            WHERE report_type='weekly' AND report_date >= CURRENT_DATE - INTERVAL '30 days'
            """,
        )
    upcoming_30 = len(ComplianceLifecycleRepository.get_upcoming_milestones(days=30, limit=10000))

    stages = [
        {
            "key": "source_collection",
            "title": "信息采集",
            "subtitle": "官方源 / PDF / 正文页",
            "primary_value": source_candidates,
            "primary_label": "待抓候选",
            "health": _stage_health(artifacts_downloaded, artifacts_failed),
            "metrics": [
                {"label": "已抓工件", "value": artifacts_downloaded},
                {"label": "抓取失败", "value": artifacts_failed},
            ],
        },
        {
            "key": "evidence_review",
            "title": "证据核实",
            "subtitle": "真实性审核 / 人工补源",
            "primary_value": review_verified,
            "primary_label": "审核 verified",
            "health": _stage_health(review_verified, review_suspicious),
            "metrics": [
                {"label": "suspicious", "value": review_suspicious},
                {"label": "quarantined", "value": review_quarantined},
            ],
        },
        {
            "key": "knowledge_deposit",
            "title": "知识库沉淀",
            "subtitle": "法规 / 认证 / 标准",
            "primary_value": verified_records,
            "primary_label": "正式条目",
            "health": _stage_health(verified_records),
            "metrics": [
                {"label": "ready 文档", "value": ready_documents},
                {"label": "切片", "value": chunks},
            ],
        },
        {
            "key": "spec_output",
            "title": "规格输出",
            "subtitle": "产品要求 / 研发测试清单",
            "primary_value": spec_requirements,
            "primary_label": "规格要求",
            "health": _stage_health(spec_requirements),
            "metrics": [
                {"label": "已解析文档", "value": parsed_documents},
                {"label": "含规格文档", "value": docs_with_specs},
            ],
        },
        {
            "key": "query_use",
            "title": "查询使用",
            "subtitle": "后台 / 飞书 / RAG 问答",
            "primary_value": ready_documents,
            "primary_label": "可问答文档",
            "health": _stage_health(ready_documents),
            "metrics": [
                {"label": "verified 条目", "value": verified_records},
                {"label": "RAG 切片", "value": chunks},
            ],
        },
        {
            "key": "alerts_weekly",
            "title": "预警与周报",
            "subtitle": "生效提醒 / 变更记录",
            "primary_value": upcoming_30,
            "primary_label": "30天预警",
            "health": _stage_health(weekly_reports, pending_changes),
            "metrics": [
                {"label": "待审变更", "value": pending_changes},
                {"label": "30天周报", "value": weekly_reports},
            ],
        },
    ]
    return {
        "principle": "只让官方证据闭环进入 verified；AI 只基于已入库原文和切片解析、问答、规格提取。",
        "feedback": "预警和周报暴露出的异常条目回流到证据核实，不直接污染正式库。",
        "stages": stages,
    }


@router.get("/stats-full")
async def get_stats(current_user: str = Depends(require_admin_user)):
    """仪表盘核心统计数据"""
    with get_cursor() as cur:
        verified_scope = "FROM compliance_index WHERE status='active' AND authenticity_status='verified'"

        # verified 总条数
        cur.execute(f"SELECT COUNT(*) AS cnt {verified_scope}")
        total = cur.fetchone()["cnt"]

        # verified 覆盖国家数
        cur.execute(f"SELECT COUNT(DISTINCT country_code) AS cnt {verified_scope}")
        country_count = cur.fetchone()["cnt"]

        # 按类型分布
        cur.execute(f"""
            SELECT entry_type, COUNT(*) AS cnt
            {verified_scope}
            GROUP BY entry_type
        """)
        by_type = {r["entry_type"]: r["cnt"] for r in cur.fetchall()}

        # 按强制/自愿分布
        cur.execute(f"""
            SELECT mandatory, COUNT(*) AS cnt
            {verified_scope}
            GROUP BY mandatory
        """)
        by_mandatory = {r["mandatory"]: r["cnt"] for r in cur.fetchall()}

        # 本周新增/更新
        cur.execute("""
            WITH events AS (
                SELECT cl.change_type::TEXT AS change_type
                FROM change_log cl
                JOIN compliance_index ci ON cl.record_id = ci.compliance_id
                WHERE cl.changed_at >= NOW() - INTERVAL '7 days'
                  AND ci.status='active'
                  AND ci.authenticity_status='verified'
                UNION ALL
                SELECT 'created' AS change_type
                FROM compliance_index ci
                JOIN review_cases rc ON rc.id = ci.review_case_id
                WHERE rc.checked_at >= NOW() - INTERVAL '7 days'
                  AND rc.current_status='verified'
                  AND ci.status='active'
                  AND ci.authenticity_status='verified'
            )
            SELECT change_type, COUNT(*) AS cnt
            FROM events
            GROUP BY change_type
        """)
        weekly_changes = {r["change_type"]: r["cnt"] for r in cur.fetchall()}

        # 待审核变更数
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM change_log cl
            JOIN compliance_index ci ON cl.record_id = ci.compliance_id
            WHERE cl.reviewed=FALSE
              AND ci.status='active'
              AND ci.authenticity_status='verified'
        """)
        pending_review = cur.fetchone()["cnt"]

        # Top 10 国家条数
        cur.execute("""
            SELECT c.name_zh AS country_name, ci.country_code, COUNT(*) AS cnt
            FROM compliance_index ci
            JOIN countries c ON ci.country_code = c.code
            WHERE ci.status='active' AND ci.authenticity_status='verified'
            GROUP BY c.name_zh, ci.country_code
            ORDER BY cnt DESC LIMIT 10
        """)
        top_countries = [dict(r) for r in cur.fetchall()]

        # 最近任务记录
        cur.execute("""
            SELECT task_type, status, started_at, finished_at,
                   created_count, updated_count, error_count
            FROM update_tasks
            ORDER BY started_at DESC LIMIT 5
        """)
        recent_tasks = []
        for r in cur.fetchall():
            row = dict(r)
            row["started_at"] = str(row["started_at"]) if row.get("started_at") else None
            row["finished_at"] = str(row["finished_at"]) if row.get("finished_at") else None
            recent_tasks.append(row)

    upcoming_all = ComplianceLifecycleRepository.get_upcoming_milestones(days=90, limit=500)
    upcoming_count = len(upcoming_all)
    upcoming = []
    for r in upcoming_all[:10]:
        row = dict(r)
        row["effective_date"] = str(row["effective_date"]) if row.get("effective_date") else None
        row["milestone_date"] = str(row["milestone_date"]) if row.get("milestone_date") else None
        upcoming.append(row)

    return {
        "total": total,
        "country_count": country_count,
        "by_type": by_type,
        "by_mandatory": by_mandatory,
        "weekly_changes": weekly_changes,
        "pending_review": pending_review,
        "upcoming_count": upcoming_count,
        "upcoming": upcoming,
        "top_countries": top_countries,
        "recent_tasks": recent_tasks,
    }


@router.get("/upcoming")
async def get_upcoming(
    days: int = Query(90),
    country_code: Optional[str] = None,
    entry_type: Optional[str] = None,
    mandatory: Optional[str] = None,
    product_code: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    current_user: str = Depends(require_admin_user),
):
    days = _validate_upcoming_days(days)
    items = []
    for r in ComplianceLifecycleRepository.get_upcoming_milestones(
        days=days,
        country_code=country_code,
        product_code=product_code,
        entry_type=entry_type,
        mandatory=mandatory,
        keyword=keyword,
        limit=limit,
    ):
        row = dict(r)
        row["effective_date"] = str(row["effective_date"]) if row.get("effective_date") else None
        row["milestone_date"] = str(row["milestone_date"]) if row.get("milestone_date") else None
        items.append(row)
    return {"days": days, "total": len(items), "items": items}


@router.get("/recent-changes")
async def get_recent_changes(current_user: str = Depends(require_admin_user)):
    with get_cursor() as cur:
        cur.execute("""
            WITH events AS (
                SELECT cl.id::TEXT AS id,
                       cl.change_type::TEXT AS change_type,
                       cl.changed_at,
                       cl.diff_summary,
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
                SELECT rc.id::TEXT AS id,
                       'created' AS change_type,
                       rc.checked_at AS changed_at,
                       '官方证据核验通过，进入正式知识库' AS diff_summary,
                       ci.name,
                       ci.country_code,
                       c.name_zh AS country_name,
                       1 AS source_rank
                FROM compliance_index ci
                JOIN review_cases rc ON rc.id = ci.review_case_id
                JOIN countries c ON ci.country_code = c.code
                WHERE rc.current_status='verified'
                  AND ci.status='active'
                  AND ci.authenticity_status='verified'
            )
            SELECT id, change_type, changed_at, diff_summary, name, country_code, country_name
            FROM (
                SELECT DISTINCT ON (name, country_code)
                       id, change_type, changed_at, diff_summary, name, country_code, country_name, source_rank
                FROM events
                WHERE changed_at IS NOT NULL
                ORDER BY name, country_code, changed_at DESC, source_rank
            ) latest
            ORDER BY changed_at DESC
            LIMIT 15
        """)
        items = []
        for r in cur.fetchall():
            row = dict(r)
            row["changed_at"] = str(row["changed_at"]) if row.get("changed_at") else None
            items.append(row)
    return {"items": items}


@router.get("/stats")
async def get_stats_simple(current_user: str = Depends(require_admin_user)):
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM compliance_index WHERE status='active' AND authenticity_status='verified'")
        total = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(DISTINCT country_code) AS cnt FROM compliance_index WHERE status='active' AND authenticity_status='verified'")
        country_count = cur.fetchone()["cnt"]
        cur.execute("""
            WITH events AS (
                SELECT cl.id::TEXT AS event_id
                FROM change_log cl
                JOIN compliance_index ci ON cl.record_id = ci.compliance_id
                WHERE cl.change_type='created'
                  AND cl.changed_at >= NOW() - INTERVAL '7 days'
                  AND ci.status='active'
                  AND ci.authenticity_status='verified'
                UNION ALL
                SELECT rc.id::TEXT AS event_id
                FROM compliance_index ci
                JOIN review_cases rc ON rc.id = ci.review_case_id
                WHERE rc.checked_at >= NOW() - INTERVAL '7 days'
                  AND rc.current_status='verified'
                  AND ci.status='active'
                  AND ci.authenticity_status='verified'
            )
            SELECT COUNT(*) AS cnt FROM events
        """)
        created_this_week = cur.fetchone()["cnt"]
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM change_log cl
            JOIN compliance_index ci ON cl.record_id = ci.compliance_id
            WHERE cl.reviewed=FALSE
              AND ci.status='active'
              AND ci.authenticity_status='verified'
        """)
        pending_review = cur.fetchone()["cnt"]
    return {"total_records": total, "country_count": country_count,
            "created_this_week": created_this_week, "pending_review": pending_review}
