from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from admin.api.auth import require_admin_user
from collector.discovery.service import (
    AIDiscoveryService,
    CandidateValidationService,
    DiscoveryCandidateRepository,
    AIDiscoveryRunRepository,
    get_ai_discovery_candidate_repository,
    get_ai_discovery_run_repository,
    get_ai_discovery_service,
)

router = APIRouter()


class DiscoveryRunRequest(BaseModel):
    priorities: Optional[list[str]] = None
    limit_countries: int = Field(default=20, ge=1, le=240)
    queries_per_country: int = Field(default=3, ge=1, le=7)
    validation_mode: str = Field(default="ai", pattern="^(ai|manual)$")


class CandidateValidationRequest(BaseModel):
    mode: str = Field(default="manual", pattern="^(manual|ai)$")
    decision: Optional[str] = Field(default=None, pattern="^(accepted|rejected|needs_manual)$")
    reasons: list[str] = Field(default_factory=list)
    evidence_note: Optional[str] = None


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    for key in ("started_at", "finished_at", "created_at", "updated_at"):
        if item.get(key):
            item[key] = str(item[key])
    return item


def get_discovery_run_repository(request: Request) -> AIDiscoveryRunRepository:
    return getattr(request.app.state, "ai_discovery_repository", None) or get_ai_discovery_run_repository()


def get_discovery_candidate_repository(request: Request) -> DiscoveryCandidateRepository:
    return (
        getattr(request.app.state, "ai_discovery_candidate_repository", None)
        or getattr(request.app.state, "ai_discovery_repository", None)
        or get_ai_discovery_candidate_repository()
    )


def get_candidate_validation_service() -> CandidateValidationService:
    return CandidateValidationService()


@router.post("/run")
async def run_ai_discovery(
    data: DiscoveryRunRequest,
    current_user: str = Depends(require_admin_user),
    service: AIDiscoveryService = Depends(get_ai_discovery_service),
):
    try:
        return service.run(
            priorities=data.priorities,
            limit_countries=data.limit_countries,
            queries_per_country=data.queries_per_country,
            validation_mode=data.validation_mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/runs")
async def list_ai_discovery_runs(
    limit: int = 20,
    offset: int = 0,
    current_user: str = Depends(require_admin_user),
    repository: AIDiscoveryRunRepository = Depends(get_discovery_run_repository),
):
    items = [_serialize_row(row) for row in repository.list_runs(limit=limit, offset=offset)]
    return {"items": items, "total": len(items)}


@router.post("/candidates/{source_record_id}/validate")
async def validate_discovery_candidate(
    source_record_id: str,
    data: CandidateValidationRequest,
    current_user: str = Depends(require_admin_user),
    service: CandidateValidationService = Depends(get_candidate_validation_service),
):
    try:
        return service.validate(
            source_record_id,
            mode=data.mode,
            decision=data.decision,
            reasons=data.reasons,
            evidence_note=data.evidence_note,
            checked_by=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/candidates")
async def list_ai_discovery_candidates(
    limit: int = 50,
    offset: int = 0,
    country_code: Optional[str] = None,
    current_user: str = Depends(require_admin_user),
    repository: DiscoveryCandidateRepository = Depends(get_discovery_candidate_repository),
):
    items = [
        _serialize_row(row)
        for row in repository.list_candidates(limit=limit, offset=offset, country_code=country_code)
    ]
    return {"items": items, "total": len(items)}
