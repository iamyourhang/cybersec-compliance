"""
admin/api/routes/changelog.py
变更日志查看 + 人工审核接口
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query
from admin.api.auth import require_admin_user
from database.connection import get_cursor, get_connection
from database.repository import ChangeLogRepository

router = APIRouter()


@router.get("/")
async def list_changes(
    change_type: Optional[str] = None,
    country_code: Optional[str] = None,
    reviewed: Optional[bool] = None,
    sort_by: Optional[str] = Query("changed_at", regex="^(changed_at|change_type|country_code)$"),
    sort_order: Optional[str] = Query("desc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: str = Depends(require_admin_user),
):
    offset = (page - 1) * page_size
    sql = """
        SELECT cl.id, cl.record_id, cl.change_type, cl.changed_fields,
               cl.diff_summary, cl.data_source, cl.reviewed,
               cl.reviewed_by, cl.reviewed_at, cl.changed_at,
               ci.name, ci.country_code, c.name_zh AS country_name
        FROM change_log cl
        JOIN compliance_index ci ON cl.record_id = ci.compliance_id
        JOIN countries c ON ci.country_code = c.code
        WHERE ci.status='active'
          AND ci.authenticity_status='verified'
    """
    params: list = []

    if change_type:
        sql += " AND cl.change_type = %s"
        params.append(change_type)
    if country_code:
        sql += " AND ci.country_code = %s"
        params.append(country_code)
    if reviewed is not None:
        sql += " AND cl.reviewed = %s"
        params.append(reviewed)

    with get_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM ({sql}) t", params)
        total = cur.fetchone()["cnt"]

    sort_col_map = {"changed_at":"cl.changed_at","change_type":"cl.change_type","country_code":"ci.country_code"}
    sort_col = sort_col_map.get(sort_by, "cl.changed_at")
    sql += f" ORDER BY {sort_col} {sort_order.upper()} NULLS LAST LIMIT %s OFFSET %s"
    params.extend([page_size, offset])

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    items = []
    for r in rows:
        row = dict(r)
        for f in ["changed_at", "reviewed_at"]:
            if row.get(f):
                row[f] = str(row[f])
        items.append(row)

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/{log_id}/review")
async def mark_reviewed(
    log_id: int,
    current_user: str = Depends(require_admin_user),
):
    """标记变更已人工审核"""
    ChangeLogRepository.mark_reviewed(log_id, reviewed_by=current_user)
    return {"message": "已标记为已审核"}


@router.post("/review/batch")
async def batch_review(
    log_ids: list[int],
    current_user: str = Depends(require_admin_user),
):
    """批量审核"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE change_log SET reviewed=TRUE, reviewed_by=%s, reviewed_at=NOW() WHERE id=ANY(%s)",
                (current_user, log_ids),
            )
    return {"message": f"已审核 {len(log_ids)} 条"}


@router.get("/pending")
async def get_pending(current_user: str = Depends(require_admin_user)):
    """获取待审核变更"""
    rows = ChangeLogRepository.get_pending_review(limit=50)
    items = []
    for r in rows:
        row = dict(r)
        if row.get("changed_at"):
            row["changed_at"] = str(row["changed_at"])
        items.append(row)
    return {"items": items, "total": len(items)}
