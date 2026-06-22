"""
admin/api/routes/agent.py
受控网安合规 Agent API。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from admin.api.auth import get_current_user, require_admin_user
from collector.agent.service import AgentAskPayload, AgentOrchestrator
from database.repository import AgentCaseRepository

router = APIRouter()


class AgentRateLimiter:
    def __init__(self, per_minute: int = 6, per_day: int = 100):
        self.per_minute = per_minute
        self.per_day = per_day
        self._minute_hits: Dict[str, List[float]] = {}
        self._day_hits: Dict[str, List[float]] = {}

    def check(self, key: str) -> tuple[bool, Optional[str]]:
        now = time.time()
        minute_start = now - 60
        day_start = now - 86400
        minute_hits = [ts for ts in self._minute_hits.get(key, []) if ts >= minute_start]
        day_hits = [ts for ts in self._day_hits.get(key, []) if ts >= day_start]
        if len(minute_hits) >= self.per_minute:
            self._minute_hits[key] = minute_hits
            self._day_hits[key] = day_hits
            return False, "提问次数过多，请稍后再试。"
        if len(day_hits) >= self.per_day:
            self._minute_hits[key] = minute_hits
            self._day_hits[key] = day_hits
            return False, "今日提问次数已达上限，请明天再试。"
        minute_hits.append(now)
        day_hits.append(now)
        self._minute_hits[key] = minute_hits
        self._day_hits[key] = day_hits
        return True, None


AGENT_RATE_LIMITER = AgentRateLimiter()


class AgentHistoryMessageRequest(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=2000)


class AgentAskRequest(BaseModel):
    question: str = Field(min_length=2)
    country_code: Optional[str] = None
    product_code: Optional[str] = None
    document_id: Optional[str] = None
    alert_window_days: int = Field(default=90, ge=1, le=360)
    verified_only: bool = True
    history: List[AgentHistoryMessageRequest] = Field(default_factory=list)


class AgentCaseDecisionRequest(BaseModel):
    status: str
    handler_note: Optional[str] = None
    linked_source_record_id: Optional[str] = None
    linked_review_case_id: Optional[str] = None
    linked_document_id: Optional[str] = None


def get_agent_orchestrator(request: Request) -> AgentOrchestrator:
    service = getattr(request.app.state, "agent_orchestrator", None)
    if service is None:
        service = AgentOrchestrator()
        request.app.state.agent_orchestrator = service
    return service


@router.post("/ask")
async def ask_agent(
    data: AgentAskRequest,
    current_user: str = Depends(get_current_user),
    agent: AgentOrchestrator = Depends(get_agent_orchestrator),
):
    allowed, reason = AGENT_RATE_LIMITER.check(current_user)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)
    try:
        payload = data.model_dump()
        payload["verified_only"] = True
        return agent.ask(AgentAskPayload(**payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cases")
async def list_agent_cases(
    status: Optional[str] = None,
    country_code: Optional[str] = None,
    intent: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: str = Depends(require_admin_user),
):
    return AgentCaseRepository.list_filtered(
        status=status,
        country_code=country_code,
        intent=intent,
        limit=limit,
        offset=offset,
    )


@router.post("/cases/{case_id}/decision")
async def apply_agent_case_decision(
    case_id: str,
    data: AgentCaseDecisionRequest,
    current_user: str = Depends(require_admin_user),
):
    if data.status not in {"open", "triaged", "resolved", "rejected"}:
        raise HTTPException(status_code=400, detail="status 不合法")
    decision: Dict[str, Any] = data.model_dump()
    decision["handled_by"] = current_user
    return AgentCaseRepository.apply_decision(case_id, decision)
