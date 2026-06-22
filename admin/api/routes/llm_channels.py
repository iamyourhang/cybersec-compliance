"""
admin/api/routes/llm_channels.py
AI 通道管理接口
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from admin.api.auth import require_admin_user
from collector.providers.factory import build_provider_from_channel
from collector.providers.channel_repository import ChannelRepository, get_channel_repository
from collector.providers.router_models import ChannelConfig

router = APIRouter()


class ChannelUpdateRequest(BaseModel):
    name: str
    provider_type: str
    base_url: str
    api_key: Optional[str] = None
    model: str
    priority: int = 100
    enabled: bool = True
    supports_web_search: bool = False


class ChannelStatusRequest(BaseModel):
    message: Optional[str] = None


class ChannelTestRequest(ChannelUpdateRequest):
    pass


def _serialize_channel(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.pop("api_key_encrypted", None)
    for field in ("last_checked_at", "created_at", "updated_at"):
        if item.get(field):
            item[field] = str(item[field])
    return item


@router.get("/")
async def list_channels(
    current_user: str = Depends(require_admin_user),
    repository: ChannelRepository = Depends(get_channel_repository),
):
    items = [_serialize_channel(row) for row in repository.list_all()]
    return {"items": items, "total": len(items)}


@router.post("/", status_code=201)
async def create_channel(
    data: ChannelUpdateRequest,
    current_user: str = Depends(require_admin_user),
    repository: ChannelRepository = Depends(get_channel_repository),
):
    if not data.api_key:
        raise HTTPException(status_code=400, detail="新增通道时必须提供 API Key")
    item = repository.create_channel(data.model_dump())
    repository.add_event(item["id"], "created", "后台新增通道", None)
    return _serialize_channel(item)


@router.put("/{channel_id}")
async def update_channel(
    channel_id: str,
    data: ChannelUpdateRequest,
    current_user: str = Depends(require_admin_user),
    repository: ChannelRepository = Depends(get_channel_repository),
):
    item = repository.update_channel(channel_id, data.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="通道不存在")
    repository.add_event(channel_id, "updated", "后台更新通道", None)
    return _serialize_channel(item)


@router.get("/{channel_id}/events")
async def get_channel_events(
    channel_id: str,
    limit: int = 50,
    current_user: str = Depends(require_admin_user),
    repository: ChannelRepository = Depends(get_channel_repository),
):
    items = []
    for row in repository.list_events(channel_id, limit=limit):
        item = dict(row)
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])
        items.append(item)
    return {"items": items, "total": len(items)}


@router.post("/test")
async def test_channel(
    data: ChannelTestRequest,
    current_user: str = Depends(require_admin_user),
):
    if not data.api_key:
        raise HTTPException(status_code=400, detail="测试通道时必须提供 API Key")
    provider = build_provider_from_channel(
        ChannelConfig(
            id="preview",
            name=data.name,
            provider_type=data.provider_type,
            base_url=data.base_url,
            api_key=data.api_key,
            model=data.model,
            priority=data.priority,
            enabled=data.enabled,
            supports_web_search=data.supports_web_search,
        )
    )
    response = provider.chat(
        messages=[
            {"role": "system", "content": "你是一个连通性测试助手。"},
            {"role": "user", "content": "请只回复 OK"},
        ],
        temperature=0,
        max_tokens=16,
        enable_web_search=False,
    )
    return {
        "success": True,
        "provider_name": response.provider_name,
        "model": response.model,
        "content": response.content,
        "latency_ms": response.latency_ms,
    }


@router.post("/{channel_id}/test")
async def test_existing_channel(
    channel_id: str,
    current_user: str = Depends(require_admin_user),
    repository: ChannelRepository = Depends(get_channel_repository),
):
    channel = repository.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")
    try:
        provider = build_provider_from_channel(channel)
        response = provider.chat(
            messages=[
                {"role": "system", "content": "你是一个连通性测试助手。"},
                {"role": "user", "content": "请只回复 OK"},
            ],
            temperature=0,
            max_tokens=16,
            enable_web_search=False,
        )
        repository.add_event(channel_id, "connectivity_test_passed", "后台手动测试通道成功", None)
        return {
            "success": True,
            "provider_name": response.provider_name,
            "model": response.model,
            "content": response.content,
            "latency_ms": response.latency_ms,
        }
    except Exception as exc:
        repository.add_event(channel_id, "connectivity_test_failed", "后台手动测试通道失败", str(exc))
        raise HTTPException(status_code=502, detail=f"通道连通性测试失败: {exc}") from exc


@router.post("/{channel_id}/pause")
async def pause_channel(
    channel_id: str,
    req: Optional[ChannelStatusRequest] = Body(default=None),
    current_user: str = Depends(require_admin_user),
    repository: ChannelRepository = Depends(get_channel_repository),
):
    if repository.set_manual_pause(channel_id, True) is False:
        raise HTTPException(status_code=404, detail="通道不存在")
    message = req.message if req else None
    repository.add_event(channel_id, "manual_paused", message or "后台手动暂停", None)
    return {"success": True, "channel_id": channel_id}


@router.post("/{channel_id}/resume")
async def resume_channel(
    channel_id: str,
    req: Optional[ChannelStatusRequest] = Body(default=None),
    current_user: str = Depends(require_admin_user),
    repository: ChannelRepository = Depends(get_channel_repository),
):
    if repository.set_manual_pause(channel_id, False) is False:
        raise HTTPException(status_code=404, detail="通道不存在")
    message = req.message if req else None
    repository.add_event(channel_id, "manual_resumed", message or "后台恢复通道", None)
    return {"success": True, "channel_id": channel_id}


@router.post("/{channel_id}/mark-quota-exhausted")
async def mark_quota_exhausted(
    channel_id: str,
    req: Optional[ChannelStatusRequest] = Body(default=None),
    current_user: str = Depends(require_admin_user),
    repository: ChannelRepository = Depends(get_channel_repository),
):
    message = req.message if req else None
    if repository.mark_quota_exhausted(channel_id, message or "后台手动标记额度耗尽") is False:
        raise HTTPException(status_code=404, detail="通道不存在")
    repository.add_event(
        channel_id,
        "quota_exhausted_detected",
        message or "后台手动标记额度耗尽",
        message,
    )
    return {"success": True, "channel_id": channel_id}


@router.post("/{channel_id}/clear-quota-exhausted")
async def clear_quota_exhausted(
    channel_id: str,
    req: Optional[ChannelStatusRequest] = Body(default=None),
    current_user: str = Depends(require_admin_user),
    repository: ChannelRepository = Depends(get_channel_repository),
):
    if repository.clear_quota_exhausted(channel_id) is False:
        raise HTTPException(status_code=404, detail="通道不存在")
    message = req.message if req else None
    repository.add_event(channel_id, "quota_cleared", message or "后台清除额度耗尽状态", None)
    return {"success": True, "channel_id": channel_id}
