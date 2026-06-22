"""
admin/api/routes/tasks.py
任务管理：手动触发更新、查看任务历史、生成周报
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from pydantic import BaseModel

from admin.api.auth import require_admin_user
from database.connection import get_cursor

logger = logging.getLogger(__name__)
router = APIRouter()

# 防止同时触发多个任务
_running_task: Optional[str] = None
_task_lock = threading.Lock()


class TriggerRequest(BaseModel):
    countries: Optional[list[str]] = None
    priority: Optional[str] = None


def _insert_task_history(task_type: str, status: str, created_count: int, updated_count: int, error_count: int, triggered_by: str):
    from database.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO update_tasks
                   (task_type, status, finished_at, created_count, updated_count, error_count, triggered_by)
                   VALUES (%s, %s, NOW(), %s, %s, %s, %s)""",
                (task_type, status, created_count, updated_count, error_count, triggered_by),
            )


def _run_official_source_sync(countries, priority, triggered_by):
    global _running_task
    try:
        from collector.official_sources.pipeline import OfficialSourcePipeline

        pipeline = OfficialSourcePipeline()

        priorities = [priority] if priority else None
        if priorities:
            stats = pipeline.sync_country_priorities(priorities)
        else:
            stats = pipeline.sync_country_priorities(["P1", "P2", "P3"])

        _insert_task_history(
            "official_source_sync",
            "success",
            stats.get("candidate_count", 0),
            0,
            0,
            f"manual:{triggered_by}",
        )
    except Exception as e:
        logger.error("手动触发官方源同步失败: %s", e, exc_info=True)
        _insert_task_history("official_source_sync", "failed", 0, 0, 1, f"manual:{triggered_by}")
    finally:
        with _task_lock:
            global _running_task
            _running_task = None


def _run_simple_task(task_type: str, runner, triggered_by: str):
    global _running_task
    try:
        runner()
        _insert_task_history(task_type, "success", 0, 0, 0, f"manual:{triggered_by}")
    except Exception as exc:
        logger.error("手动触发任务失败 [%s]: %s", task_type, exc, exc_info=True)
        _insert_task_history(task_type, "failed", 0, 0, 1, f"manual:{triggered_by}")
    finally:
        with _task_lock:
            _running_task = None


async def _trigger_official_source_sync(
    req: TriggerRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    """手动触发官方源同步（后台异步执行）"""
    global _running_task
    with _task_lock:
        if _running_task:
            raise HTTPException(status_code=409, detail=f"任务 [{_running_task}] 正在运行，请稍后")
        _running_task = "official_source_sync"

    background_tasks.add_task(
        _run_official_source_sync, req.countries, req.priority, current_user
    )
    logger.info("手动触发官方源同步 [by %s, countries=%s, priority=%s]",
                current_user, req.countries, req.priority)
    return {"message": "官方源同步任务已启动（后台运行）", "task": "official_source_sync"}


@router.post("/trigger/official-source-sync")
async def trigger_official_source_sync(
    req: TriggerRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    return await _trigger_official_source_sync(req, background_tasks, current_user)


@router.post("/trigger/full-update")
async def trigger_full_update(
    req: TriggerRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    """兼容旧入口，语义等同官方源同步"""
    return await _trigger_official_source_sync(req, background_tasks, current_user)


@router.post("/trigger/artifact-fetch")
async def trigger_artifact_fetch(
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    global _running_task
    with _task_lock:
        if _running_task:
            raise HTTPException(status_code=409, detail=f"任务 [{_running_task}] 正在运行，请稍后")
        _running_task = "official_artifact_fetch"

    from scheduler.main import job_official_artifact_fetch

    background_tasks.add_task(_run_simple_task, "official_artifact_fetch", job_official_artifact_fetch, current_user)
    return {"message": "官方原文抓取任务已启动", "task": "official_artifact_fetch"}


@router.post("/trigger/candidate-verification")
async def trigger_candidate_verification(
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    global _running_task
    with _task_lock:
        if _running_task:
            raise HTTPException(status_code=409, detail=f"任务 [{_running_task}] 正在运行，请稍后")
        _running_task = "candidate_verification"

    from scheduler.main import job_candidate_verification

    background_tasks.add_task(_run_simple_task, "candidate_verification", job_candidate_verification, current_user)
    return {"message": "候选规则验真任务已启动", "task": "candidate_verification"}


@router.post("/trigger/document-parse")
async def trigger_document_parse(
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    global _running_task
    with _task_lock:
        if _running_task:
            raise HTTPException(status_code=409, detail=f"任务 [{_running_task}] 正在运行，请稍后")
        _running_task = "document_parse"

    from scheduler.main import job_document_parse

    background_tasks.add_task(_run_simple_task, "document_parse", job_document_parse, current_user)
    return {"message": "官方原文解析任务已启动", "task": "document_parse"}


@router.post("/trigger/read-model-refresh")
async def trigger_read_model_refresh(
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    global _running_task
    with _task_lock:
        if _running_task:
            raise HTTPException(status_code=409, detail=f"任务 [{_running_task}] 正在运行，请稍后")
        _running_task = "read_model_refresh"

    from scheduler.main import job_read_model_refresh

    background_tasks.add_task(_run_simple_task, "read_model_refresh", job_read_model_refresh, current_user)
    return {"message": "读模型刷新任务已启动", "task": "read_model_refresh"}


@router.post("/trigger/weekly-compliance-update")
async def trigger_weekly_compliance_update(
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    """手动触发每两周全球合规知识库完整更新闭环"""
    global _running_task
    with _task_lock:
        if _running_task:
            raise HTTPException(status_code=409, detail=f"任务 [{_running_task}] 正在运行，请稍后")
        _running_task = "weekly_compliance_update"

    from scheduler.main import job_weekly_compliance_update

    background_tasks.add_task(
        _run_simple_task,
        "weekly_compliance_update",
        job_weekly_compliance_update,
        current_user,
    )
    return {"message": "每两周全球合规知识库更新任务已启动", "task": "weekly_compliance_update"}


@router.post("/trigger/source-registry-refresh")
async def trigger_source_registry_refresh(
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    global _running_task
    with _task_lock:
        if _running_task:
            raise HTTPException(status_code=409, detail=f"任务 [{_running_task}] 正在运行，请稍后")
        _running_task = "source_registry_refresh"

    from scheduler.main import job_global_source_registry_refresh

    background_tasks.add_task(
        _run_simple_task,
        "source_registry_refresh",
        job_global_source_registry_refresh,
        current_user,
    )
    return {"message": "全球官方源覆盖矩阵刷新任务已启动", "task": "source_registry_refresh"}


@router.post("/trigger/weekly-report")
async def trigger_weekly_report(
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    """手动触发周报生成"""
    def _run():
        try:
            from scheduler.main import job_weekly_report
            job_weekly_report()
        except Exception as e:
            logger.error("手动触发周报失败: %s", e)

    background_tasks.add_task(_run)
    return {"message": "周报生成任务已启动"}


@router.post("/trigger/alert-scan")
async def trigger_alert_scan(
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin_user),
):
    """手动触发预警扫描"""
    def _run():
        try:
            from notifier.alert_scanner import AlertScanner
            AlertScanner().run()
        except Exception as e:
            logger.error("手动触发预警扫描失败: %s", e)

    background_tasks.add_task(_run)
    return {"message": "预警扫描已启动"}


@router.get("/status")
async def get_task_status(current_user: str = Depends(require_admin_user)):
    """当前任务运行状态"""
    return {"running_task": _running_task}


@router.get("/history")
async def get_task_history(
    limit: int = 20,
    current_user: str = Depends(require_admin_user),
):
    """任务执行历史"""
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, task_type, status, started_at, finished_at,
                      created_count, updated_count, error_count, triggered_by
               FROM update_tasks ORDER BY started_at DESC LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()

    items = []
    for r in rows:
        row = dict(r)
        for f in ["started_at", "finished_at"]:
            if row.get(f):
                row[f] = str(row[f])
        items.append(row)
    return {"items": items}


@router.get("/reports")
async def get_report_history(
    limit: int = 20,
    current_user: str = Depends(require_admin_user),
):
    """报告生成历史"""
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, report_type, report_date, file_name, cos_url,
                      feishu_sent, generated_at
               FROM report_records ORDER BY generated_at DESC LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()

    items = []
    for r in rows:
        row = dict(r)
        for f in ["report_date", "generated_at", "feishu_sent_at"]:
            if row.get(f):
                row[f] = str(row[f])
        items.append(row)
    return {"items": items}
