from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from admin.api.auth import require_admin_user
from collector.official_sources.pipeline import OfficialSourcePipeline, get_official_source_pipeline
from collector.official_sources.repository import OfficialSourceRepository, get_official_source_repository

router = APIRouter()


class OfficialSourceRequest(BaseModel):
    country_code: str
    name: str
    base_url: str
    list_url: str
    source_type: str
    allowed_domains: list[str] = Field(default_factory=list)
    entry_type_scope: list[str] = Field(default_factory=list)
    poll_interval_hours: int = 24
    priority: int = 100
    enabled: bool = True
    parser_config: dict[str, Any] = Field(default_factory=dict)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    for field in ("last_checked_at", "last_success_at", "created_at", "updated_at", "started_at"):
        if item.get(field):
            item[field] = str(item[field])
    return item


@router.get("/")
async def list_official_sources(
    country_priority: Optional[str] = None,
    current_user: str = Depends(require_admin_user),
    repository: OfficialSourceRepository = Depends(get_official_source_repository),
):
    priorities = [country_priority] if country_priority else None
    items = [_serialize_row(row) for row in repository.list_all(country_priorities=priorities)]
    return {"items": items, "total": len(items)}


@router.post("/", status_code=201)
async def create_official_source(
    data: OfficialSourceRequest,
    current_user: str = Depends(require_admin_user),
    repository: OfficialSourceRepository = Depends(get_official_source_repository),
):
    item = repository.create(data.model_dump())
    return _serialize_row(item)


@router.put("/{source_id}")
async def update_official_source(
    source_id: str,
    data: OfficialSourceRequest,
    current_user: str = Depends(require_admin_user),
    repository: OfficialSourceRepository = Depends(get_official_source_repository),
):
    item = repository.update(source_id, data.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="官方源不存在")
    return _serialize_row(item)


@router.post("/{source_id}/sync")
async def sync_official_source(
    source_id: str,
    current_user: str = Depends(require_admin_user),
    pipeline: OfficialSourcePipeline = Depends(get_official_source_pipeline),
):
    try:
        return pipeline.sync_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{source_id}/history")
async def get_official_source_history(
    source_id: str,
    limit: int = 20,
    current_user: str = Depends(require_admin_user),
    repository: OfficialSourceRepository = Depends(get_official_source_repository),
):
    items = [_serialize_row(row) for row in repository.list_history(source_id, limit=limit)]
    return {"items": items, "total": len(items)}
