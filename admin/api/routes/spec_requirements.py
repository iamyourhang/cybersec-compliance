from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from admin.api.auth import get_current_user
from database.repository import RegulationSpecRequirementRepository

router = APIRouter()


@router.get("/")
async def list_spec_requirements(
    document_id: Optional[str] = None,
    country_code: Optional[str] = None,
    product_code: Optional[str] = None,
    priority: Optional[str] = None,
    regulation_clause: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    current_user: str = Depends(get_current_user),
):
    items = RegulationSpecRequirementRepository.list_filtered(
        document_id=document_id,
        country_code=country_code,
        product_code=product_code,
        priority=priority,
        regulation_clause=regulation_clause,
        limit=limit,
    )
    return {"items": items, "total": len(items)}
