"""
admin/api/routes/settings.py
系统设置：预警规则、国家/产品管理
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from admin.api.auth import require_admin_user
from database.connection import get_cursor, get_connection

router = APIRouter()


# ---- 预警规则 ----

# alert-rules GET 已在底部统一定义


class AlertRuleUpdate(BaseModel):
    enabled: bool


@router.put("/alert-rules/{rule_id}")
async def update_alert_rule(
    rule_id: int,
    data: AlertRuleUpdate,
    current_user: str = Depends(require_admin_user),
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE alert_rules SET enabled=%s WHERE id=%s",
                (data.enabled, rule_id),
            )
    return {"message": "更新成功"}


# ---- 国家管理 ----

@router.get("/countries")
async def get_countries(current_user: str = Depends(require_admin_user)):
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.*, COUNT(ci.id) AS record_count
            FROM countries c
            LEFT JOIN compliance_index ci
              ON ci.country_code=c.code
             AND ci.status='active'
             AND ci.authenticity_status='verified'
            GROUP BY c.id ORDER BY c.priority, c.name_zh
        """)
        rows = cur.fetchall()
    items = []
    for r in rows:
        row = dict(r)
        for f in ["created_at", "updated_at"]:
            if row.get(f):
                row[f] = str(row[f])
        items.append(row)
    return items


class CountryPriorityUpdate(BaseModel):
    priority: str  # P1/P2/P3
    enabled: Optional[bool] = None


@router.put("/countries/{code}")
async def update_country(
    code: str,
    data: CountryPriorityUpdate,
    current_user: str = Depends(require_admin_user),
):
    updates = ["priority=%s"]
    params = [data.priority]
    if data.enabled is not None:
        updates.append("enabled=%s")
        params.append(data.enabled)
    params.append(code)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE countries SET {', '.join(updates)} WHERE code=%s",
                params,
            )
    return {"message": "更新成功"}


# ---- 产品管理 ----

@router.get("/products")
async def get_products(current_user: str = Depends(require_admin_user)):
    with get_cursor() as cur:
        cur.execute("""
            SELECT p.*, COUNT(DISTINCT ci.id) AS record_count
            FROM products p
            LEFT JOIN compliance_index ci
              ON p.code=ANY(ci.applicable_products)
             AND ci.status='active'
             AND ci.authenticity_status='verified'
            GROUP BY p.id ORDER BY p.name_zh
        """)
        rows = cur.fetchall()
    items = []
    for r in rows:
        row = dict(r)
        for f in ["created_at", "updated_at"]:
            if row.get(f):
                row[f] = str(row[f])
        items.append(row)
    return items


class ProductToggle(BaseModel):
    enabled: bool


@router.put("/products/{code}")
async def update_product(
    code: str,
    data: ProductToggle,
    current_user: str = Depends(require_admin_user),
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE products SET enabled=%s WHERE code=%s",
                (data.enabled, code),
            )
    return {"message": "更新成功"}


# ---- API Key 管理 ----

class ApiKeyCreate(BaseModel):
    provider: str
    model: str
    api_key: str
    base_url: str
    priority: int = 1


@router.get("/api-keys")
async def get_api_keys(current_user: str = Depends(require_admin_user)):
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, provider, model, base_url, enabled, priority, notes, created_at
            FROM api_configs ORDER BY priority
        """)
        rows = cur.fetchall()
    items = []
    for r in rows:
        row = dict(r)
        if row.get("created_at"):
            row["created_at"] = str(row["created_at"])
        items.append(row)
    return {"items": items}


@router.post("/api-keys", status_code=201)
async def create_api_key(
    data: ApiKeyCreate,
    current_user: str = Depends(require_admin_user),
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO api_configs
                   (provider, model, api_key_encrypted, base_url, priority, enabled)
                   VALUES (%s, %s, %s, %s, %s, TRUE)""",
                (data.provider, data.model, data.api_key, data.base_url, data.priority),
            )
    return {"message": "添加成功"}


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: int,
    current_user: str = Depends(require_admin_user),
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM api_configs WHERE id=%s", (key_id,))
    return {"message": "已删除"}


# ---- 预警规则返回格式修正 ----

@router.get("/alert-rules")
async def get_alert_rules_list(current_user: str = Depends(require_admin_user)):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM alert_rules ORDER BY id")
        return {"items": [dict(r) for r in cur.fetchall()]}
