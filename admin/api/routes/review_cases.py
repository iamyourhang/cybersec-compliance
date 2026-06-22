from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from admin.api.auth import require_admin_user
from collector.review.service import get_authenticity_review_service

router = APIRouter()


class ReviewDecisionRequest(BaseModel):
    authenticity_status: str
    risk_score: int
    reasons: List[str]
    evidence_note: str
    source_download_status: Optional[str] = None
    source_download_error: Optional[str] = None


class ReviewAIVerifyDryRunRequest(BaseModel):
    current_status: str = "suspicious"
    country_code: Optional[str] = None
    limit: int = 10


@router.get("/")
async def list_review_cases(
    current_status: Optional[str] = None,
    country_code: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: str = Depends(require_admin_user),
):
    service = get_authenticity_review_service()
    return service.list_cases(
        current_status=current_status,
        country_code=country_code,
        limit=limit,
    )


@router.post("/{case_id}/decision")
async def apply_review_decision(
    case_id: str,
    req: ReviewDecisionRequest,
    current_user: str = Depends(require_admin_user),
):
    if req.authenticity_status not in {"candidate", "suspicious", "quarantined", "verified"}:
        raise HTTPException(status_code=400, detail="authenticity_status 不合法")
    if not req.reasons:
        raise HTTPException(status_code=400, detail="reasons 不能为空")
    if not req.evidence_note.strip():
        raise HTTPException(status_code=400, detail="evidence_note 不能为空")
    if not 0 <= req.risk_score <= 100:
        raise HTTPException(status_code=400, detail="risk_score 必须在 0-100 之间")

    service = get_authenticity_review_service()
    return service.apply_decision(case_id, req.model_dump(), checked_by=current_user)


@router.post("/ai-verify-dry-run")
async def dry_run_review_ai_verification(
    req: ReviewAIVerifyDryRunRequest,
    current_user: str = Depends(require_admin_user),
):
    if req.current_status not in {"candidate", "suspicious"}:
        raise HTTPException(status_code=400, detail="current_status 只允许 candidate 或 suspicious")
    if not 1 <= req.limit <= 50:
        raise HTTPException(status_code=400, detail="limit 必须在 1-50 之间")
    service = get_authenticity_review_service()
    return service.dry_run_authenticity_verification(
        current_status=req.current_status,
        country_code=req.country_code,
        limit=req.limit,
    )


@router.post("/{case_id}/ai-assist")
async def generate_review_ai_assist(
    case_id: str,
    current_user: str = Depends(require_admin_user),
):
    service = get_authenticity_review_service()
    return service.generate_ai_assist(case_id)
