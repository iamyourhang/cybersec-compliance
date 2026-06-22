"""
admin/api/routes/documents.py
法规原文文档管理接口 - 独立模块，不修改任何现有路由
"""
from __future__ import annotations
import logging, uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel
from admin.api.auth import get_current_user, is_admin_username, require_admin_user
from collector.document.cos_storage import CosStorage
from collector.document.doc_repository import DocRepository
from collector.document.index_service import DocumentIndexService
from collector.document.parse_service import DocumentParseService
from database.repository import (
    CanonicalRequirementRepository,
    ComplianceRepository,
    RegulationChunkRepository,
    RegulationSectionRepository,
    RegulationSpecRequirementRepository,
    ReviewCaseRepository,
    SourceArtifactRepository,
)
from config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _extract_index_diagnostics(doc: dict) -> dict:
    parse_result = doc.get("parse_result") or {}
    diagnostics = parse_result.get("index_diagnostics") or {}
    return {
        "parsed_count": int(diagnostics.get("parsed_count", 0) or 0),
        "filtered_count": int(diagnostics.get("filtered_count", 0) or 0),
        "filtered_reason_summary": diagnostics.get("filtered_reason_summary") or {},
    }


def _serialize(rows):
    """统一处理日期字段序列化"""
    result = []
    for r in (rows if isinstance(rows, list) else [rows]):
        row = dict(r)
        for f in ["created_at", "parsed_at", "indexed_at", "spec_generated_at"]:
            if row.get(f): row[f] = str(row[f])
        result.append(row)
    return result


def _enrich_document(doc: dict) -> dict:
    payload = _serialize([doc])[0]
    doc_id = str(payload["id"])
    compliance_id = str(payload["compliance_id"]) if payload.get("compliance_id") else None

    canonical = CanonicalRequirementRepository.get_by_document_id(doc_id)
    review_case = ReviewCaseRepository.get_by_compliance_id(compliance_id) if compliance_id else None
    source_artifacts = SourceArtifactRepository.list_by_entity(doc_id)
    spec_requirement_count = RegulationSpecRequirementRepository.count_by_document(doc_id)

    linked_record = ComplianceRepository.get_by_id(compliance_id) if compliance_id else None
    authenticity_status = payload.get("authenticity_status")
    if not authenticity_status and review_case:
        authenticity_status = review_case.get("current_status")
    if not authenticity_status and linked_record:
        authenticity_status = linked_record.get("authenticity_status")
    if not authenticity_status and canonical:
        authenticity_status = canonical.get("verification_status")
    authenticity_status = authenticity_status or "candidate"

    payload.update(
        {
            "authenticity_status": authenticity_status,
            "authenticity_risk_score": (
                review_case.get("risk_score")
                if review_case and review_case.get("risk_score") is not None
                else payload.get("authenticity_risk_score")
            ),
            "canonical_requirement_id": canonical.get("id") if canonical else None,
            "canonical_requirement_name": canonical.get("name") if canonical else None,
            "canonical_verification_status": canonical.get("verification_status") if canonical else None,
            "review_case_id": review_case.get("id") if review_case else None,
            "review_case_status": review_case.get("current_status") if review_case else None,
            "source_artifact_count": len(source_artifacts),
            "source_artifacts": [
                _serialize([item])[0] if isinstance(item, dict) else item
                for item in source_artifacts
            ],
            "spec_requirement_count": max(int(payload.get("spec_requirement_count") or 0), spec_requirement_count),
            "is_verified_document": authenticity_status == "verified"
            or bool(canonical and canonical.get("verification_status") == "verified"),
        }
    )
    return payload


def _parse_and_index_document(doc_id: str, write_to_knowledge: bool = True) -> None:
    try:
        parse_result = DocumentParseService().parse_document(doc_id, write_to_knowledge=write_to_knowledge)
        if not parse_result.get("success"):
            return
        DocumentIndexService().index_document(doc_id)
    except Exception as e:
        logger.error("后台解析/索引失败 [%s]: %s", doc_id, e, exc_info=True)
        DocRepository.set_index_failed(doc_id, str(e))


def _generate_spec_document(doc_id: str, applicable_products: Optional[list]) -> None:
    try:
        from collector.document.spec_generator import SpecGeneratorService

        SpecGeneratorService().generate_from_doc(
            doc_id=doc_id,
            applicable_products=applicable_products,
        )
    except Exception as exc:
        logger.error("后台规格生成失败 [%s]: %s", doc_id, exc, exc_info=True)
        DocRepository.set_spec_progress(doc_id, 0, f"失败: {str(exc)[:100]}")


@router.get("/")
async def list_documents(
    country_code: Optional[str] = None,
    parse_status: Optional[str] = None,
    index_status: Optional[str] = None,
    limit: int = 50,
    current_user: str = Depends(get_current_user),
):
    """列出所有文档记录"""
    items = DocRepository.list(
        country_code=country_code,
        parse_status=parse_status,
        index_status=index_status,
        limit=limit,
    )
    enriched = [_enrich_document(item) for item in items]
    if not is_admin_username(current_user):
        enriched = [item for item in enriched if item.get("is_verified_document")]
    return {"items": enriched, "total": len(enriched)}


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(...),
    country_code: str = Form(...),
    auto_parse: bool = Form(True),
    current_user: str = Depends(require_admin_user),
):
    """
    上传法规原文PDF到COS，可选自动触发解析。
    auto_parse=True 时后台异步解析，不阻塞响应。
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持PDF文件")

    # 限制文件大小 50MB
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过50MB")

    # 上传到 COS
    s = get_settings()
    cos_key = f"{s.cos.report_prefix}documents/{country_code}/{uuid.uuid4().hex}_{file.filename}"
    cos = CosStorage()
    cos_url = cos.upload_bytes(content, cos_key)

    # 创建数据库记录
    doc_id = DocRepository.create({
        "name": name,
        "country_code": country_code.upper(),
        "file_name": file.filename,
        "cos_key": cos_key,
        "cos_url": cos_url,
        "file_size": len(content),
        "file_type": "pdf",
        "uploaded_by": current_user,
    })

    # 自动解析
    if auto_parse:
        background_tasks.add_task(_parse_and_index_document, doc_id, False)

    logger.info("📤 文档上传: %s [%s] by %s", name, doc_id, current_user)
    return {
        "doc_id": doc_id,
        "cos_url": cos_url,
        "file_size": len(content),
        "auto_parse": auto_parse,
        "message": "上传成功" + ("，已触发后台解析" if auto_parse else ""),
    }


@router.post("/{doc_id}/parse")
async def trigger_parse(
    doc_id: str,
    background_tasks: BackgroundTasks,
    write_to_knowledge: bool = False,
    current_user: str = Depends(require_admin_user),
):
    """手动触发文档解析（后台异步执行）"""
    doc = DocRepository.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc["parse_status"] == "parsing":
        raise HTTPException(status_code=409, detail="文档正在解析中")

    background_tasks.add_task(_parse_and_index_document, doc_id, write_to_knowledge)
    return {"message": "解析任务已启动（后台运行）", "doc_id": doc_id}


@router.post("/{doc_id}/index")
async def trigger_index(
    doc_id: str,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    doc = DocRepository.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    def _index():
        try:
            DocumentIndexService().index_document(doc_id)
        except Exception as e:
            logger.error("手动重建索引失败 [%s]: %s", doc_id, e, exc_info=True)
            DocRepository.set_index_failed(doc_id, str(e))

    background_tasks.add_task(_index)
    return {"message": "索引重建任务已启动（后台运行）", "doc_id": doc_id}


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    current_user: str = Depends(get_current_user),
):
    """获取文档详情（含解析结果）"""
    doc = DocRepository.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    payload = _enrich_document(doc)
    if not is_admin_username(current_user) and not payload.get("is_verified_document"):
        raise HTTPException(status_code=404, detail="文档不存在")
    return payload


@router.get("/{doc_id}/chunks")
async def get_document_chunks(
    doc_id: str,
    limit: int = 50,
    current_user: str = Depends(get_current_user),
):
    doc = DocRepository.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not is_admin_username(current_user) and not _enrich_document(doc).get("is_verified_document"):
        raise HTTPException(status_code=404, detail="文档不存在")
    items = RegulationChunkRepository.list_by_document(doc_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/{doc_id}/sections")
async def get_document_sections(
    doc_id: str,
    limit: int = 100,
    current_user: str = Depends(get_current_user),
):
    doc = DocRepository.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not is_admin_username(current_user) and not _enrich_document(doc).get("is_verified_document"):
        raise HTTPException(status_code=404, detail="文档不存在")
    items = RegulationSectionRepository.list_by_document(doc_id, limit=limit)
    diagnostics = _extract_index_diagnostics(doc)
    return {
        "items": items,
        "total": len(items),
        "parsed_count": diagnostics["parsed_count"],
        "filtered_count": diagnostics["filtered_count"],
        "filtered_reason_summary": diagnostics["filtered_reason_summary"],
    }


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: str = Depends(require_admin_user),
):
    """删除文档（同时删除COS文件）"""
    cos_key = DocRepository.delete(doc_id)
    if not cos_key:
        raise HTTPException(status_code=404, detail="文档不存在")
    try:
        CosStorage().delete(cos_key)
    except Exception as e:
        logger.warning("COS文件删除失败（记录已删）: %s", e)
    logger.info("🗑️  文档删除: %s by %s", doc_id, current_user)
    return {"message": "已删除"}


# ============================================================
# 规格生成接口（独立追加，不影响现有接口）
# ============================================================

class SpecRequest(BaseModel):
    applicable_products: Optional[list] = None  # None = 全部产品


@router.post("/{doc_id}/generate-spec")
async def generate_spec(
    doc_id: str,
    req: SpecRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    """
    从已上传的法规PDF生成产品规格要求Excel，上传到COS。
    改为后台异步执行，前端通过轮询文档详情查看进度。
    """
    doc = DocRepository.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc["parse_status"] not in ("done", "pending", "failed"):
        raise HTTPException(status_code=409, detail="文档状态异常")
    spec_progress = int(doc.get("spec_progress") or 0)
    if 0 < spec_progress < 100:
        raise HTTPException(status_code=409, detail="规格生成任务正在进行中")
    try:
        linked = None
        if doc.get("compliance_id"):
            linked = ComplianceRepository.get_by_id(str(doc["compliance_id"]))
        canonical = CanonicalRequirementRepository.get_by_document_id(doc_id)
        is_verified = bool(linked and linked.get("authenticity_status") == "verified")
        if canonical and canonical.get("verification_status") == "verified":
            is_verified = True
        if not is_verified:
            raise HTTPException(status_code=409, detail="仅允许对已验证文档生成规格")

        DocRepository.reset_spec_progress(doc_id, "规格生成任务已启动")
        DocRepository.set_spec_progress(doc_id, 3, "规格生成任务已启动")
        background_tasks.add_task(_generate_spec_document, doc_id, req.applicable_products)
        logger.info("📊 规格生成任务已启动 [%s] by %s", doc_id, current_user)
        return {
            "message": "规格生成任务已启动（后台运行）",
            "doc_id": doc_id,
            "doc_name": doc["name"],
            "spec_progress": 3,
            "spec_progress_msg": "规格生成任务已启动",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
