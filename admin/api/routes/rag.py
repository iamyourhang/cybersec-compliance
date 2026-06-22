"""
admin/api/routes/rag.py
法规原文 RAG 问答接口。
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from admin.api.auth import get_current_user
from collector.document.rag_service import AskPayload, RAGService

router = APIRouter()


class HistoryMessageRequest(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=2000)


class AskRequest(BaseModel):
    question: str = Field(min_length=5)
    country_code: Optional[str] = None
    product_code: Optional[str] = None
    document_id: Optional[str] = None
    top_k: int = Field(default=6, ge=1, le=10)
    verified_only: bool = True
    history: List[HistoryMessageRequest] = Field(default_factory=list)


def get_rag_service(request: Request) -> RAGService:
    service = getattr(request.app.state, "rag_service", None)
    if service is None:
        service = RAGService()
        request.app.state.rag_service = service
    return service


@router.post("/ask")
async def ask_rag(
    data: AskRequest,
    current_user: str = Depends(get_current_user),
    rag_service: RAGService = Depends(get_rag_service),
):
    try:
        payload = data.model_dump()
        # 问答属于对外交付面，固定只使用 verified 本地原文语料。
        payload["verified_only"] = True
        return rag_service.ask(AskPayload(**payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
