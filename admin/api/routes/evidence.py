from __future__ import annotations

from fastapi import APIRouter, Depends

from admin.api.auth import get_current_user
from collector.review.service import get_authenticity_review_service

router = APIRouter()


@router.get("/{entity_id}")
async def get_evidence(entity_id: str, current_user: str = Depends(get_current_user)):
    service = get_authenticity_review_service()
    return service.get_evidence(entity_id)
