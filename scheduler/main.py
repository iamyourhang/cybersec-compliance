"""
scheduler/main.py
APScheduler 调度器主程序
- 每天凌晨：关键法规倒计时刷新、官方源/原文/解析/规格/预警分层任务
- 每周：AI 官方候选发现
- 每两周：证据驱动完整闭环生成 Excel 并发送飞书
"""

from __future__ import annotations

import logging
import signal
import sys
import json
from math import ceil
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import setup_logging
from config.settings import get_settings
from database.connection import get_cursor, get_connection, health_check
from database.repository import ComplianceLifecycleRepository

setup_logging(level="INFO")
logger = logging.getLogger(__name__)
BIWEEKLY_UPDATE_START = datetime(2026, 5, 4, 1, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
WEEKLY_AI_DISCOVERY_PRIORITIES = ["P1", "P2", "P3"]
WEEKLY_AI_DISCOVERY_LIMIT_COUNTRIES = 320
WEEKLY_AI_DISCOVERY_QUERIES_PER_COUNTRY = 6
WEEKLY_AI_DISCOVERY_CRON = "30 0 * * 1"

# Backward-compatible aliases for manual callers and older tests/scripts.
DAILY_AI_DISCOVERY_PRIORITIES = WEEKLY_AI_DISCOVERY_PRIORITIES
DAILY_AI_DISCOVERY_LIMIT_COUNTRIES = WEEKLY_AI_DISCOVERY_LIMIT_COUNTRIES
DAILY_AI_DISCOVERY_QUERIES_PER_COUNTRY = WEEKLY_AI_DISCOVERY_QUERIES_PER_COUNTRY


def get_official_source_pipeline():
    from collector.official_sources.pipeline import get_official_source_pipeline as _factory

    return _factory()


# ============================================================
# 任务函数
# ============================================================

def job_official_source_sync_daily() -> None:
    """每日同步全球官方源，作为日报的确定性主来源。"""
    logger.info("⏰ [调度] 开始每日官方源同步（P1/P2/P3）")
    stats = get_official_source_pipeline().sync_country_priorities(["P1", "P2", "P3"])
    logger.info("⏰ [调度] 每日官方源同步完成: %s", stats)


def job_official_source_sync_weekly() -> None:
    """每周同步 P2/P3 国家官方源"""
    logger.info("⏰ [调度] 开始每周官方源同步（P2/P3）")
    stats = get_official_source_pipeline().sync_country_priorities(["P2", "P3"])
    logger.info("⏰ [调度] 每周官方源同步完成: %s", stats)


def job_official_artifact_fetch(limit: int = 20) -> dict:
    """抓取官方原文工件到 COS"""
    logger.info("⏰ [调度] 开始抓取官方原文工件")
    from collector.document.source_ingest import OfficialSourceIngestService
    from database.repository import SourceArtifactRepository, SourceRecordRepository

    service = OfficialSourceIngestService()
    items = SourceRecordRepository.list_pending_artifact_records(limit=limit)
    success = 0
    for item in items:
        try:
            service.ingest_record(item, requested_by="system:official_source")
            success += 1
        except Exception as exc:
            logger.warning("工件抓取失败 [%s]: %s", item.get("name"), exc)
            SourceArtifactRepository.upsert_for_compliance(
                compliance_id=item.get("compliance_id"),
                official_url=item.get("source_url"),
                artifact_url=item.get("artifact_url") or item.get("source_url"),
                artifact_type=None,
                artifact_sha256=None,
                download_status="failed",
                download_error=str(exc),
                source_record_id=str(item["id"]),
            )
    result = {"success": success, "total": len(items)}
    logger.info("⏰ [调度] 官方原文工件抓取完成: %s", result)
    return result


def job_candidate_verification(limit: int = 50) -> dict:
    """为已有关联条目的 source candidates 建立审核桶，不自动放行 verified"""
    logger.info("⏰ [调度] 开始候选审核分桶")
    from database.repository import (
        CanonicalRequirementRepository,
        ComplianceIndexRepository,
        ComplianceRepository,
        ReviewCaseRepository,
        SourceRecordRepository,
    )

    items = SourceRecordRepository.list_bucketable_records(limit=limit)
    bucketed = 0
    for item in items:
        compliance_id = item.get("compliance_id")
        if not compliance_id:
            continue
        record = ComplianceRepository.get_by_id(str(compliance_id))
        if not record:
            continue
        ReviewCaseRepository.ensure_for_record(record)
        CanonicalRequirementRepository.upsert_from_compliance(
            record,
            verification_status="verified"
            if (record.get("authenticity_status") or "candidate") == "verified"
            else "candidate",
        )
        ComplianceIndexRepository.refresh_for_compliance(record)
        bucketed += 1
    result = {"bucketed": bucketed, "total": len(items)}
    logger.info("⏰ [调度] 候选审核分桶完成: %s", result)
    return result


def job_document_parse(limit: int = 10) -> dict:
    """解析已抓取的官方原文文档"""
    logger.info("⏰ [调度] 开始解析官方原文文档")
    from collector.document.doc_repository import DocRepository
    from admin.api.routes.documents import _parse_and_index_document

    docs = DocRepository.list_pending_source_documents(limit=limit)
    for doc in docs:
        _parse_and_index_document(str(doc["id"]), False)
    result = {"total": len(docs)}
    logger.info("⏰ [调度] 官方原文文档解析完成: %s", result)
    return result


def _list_verified_documents_needing_specs(limit: int = 10) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT d.id
            FROM regulation_documents d
            JOIN compliance_index ci ON ci.compliance_id = d.compliance_id
            WHERE d.index_status='ready'
              AND d.parse_status='done'
              AND ci.status='active'
              AND ci.authenticity_status='verified'
              AND COALESCE(d.spec_requirement_count, 0) = 0
              AND d.cos_key IS NOT NULL
            ORDER BY d.indexed_at ASC NULLS LAST, d.created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def job_spec_generate(limit: int = 10) -> dict:
    """只对 verified 官方原文生成规格要求。"""
    logger.info("⏰ [调度] 开始生成 verified 原文规格")
    from collector.document.spec_generator import SpecGeneratorService

    docs = _list_verified_documents_needing_specs(limit)
    service = SpecGeneratorService()
    generated = 0
    failed = 0
    for doc in docs:
        try:
            service.generate_from_doc(str(doc["id"]))
            generated += 1
        except Exception as exc:
            failed += 1
            logger.warning("规格生成失败 [%s]: %s", doc.get("id"), exc)
    result = {"total": len(docs), "generated": generated, "failed": failed}
    logger.info("⏰ [调度] verified 原文规格生成完成: %s", result)
    return result


def job_read_model_refresh(limit: int = 200) -> dict:
    """刷新兼容读模型，供后台/飞书/RAG 统一消费"""
    logger.info("⏰ [调度] 开始刷新读模型")
    from database.connection import get_cursor
    from database.repository import ComplianceIndexRepository, ComplianceRepository

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM compliance_knowledge
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        ids = [str(row["id"]) for row in cur.fetchall()]

    refreshed = 0
    for compliance_id in ids:
        record = ComplianceRepository.get_by_id(compliance_id)
        if not record:
            continue
        ComplianceIndexRepository.refresh_for_compliance(record)
        refreshed += 1
    result = {"refreshed": refreshed, "total": len(ids)}
    logger.info("⏰ [调度] 读模型刷新完成: %s", result)
    return result


def job_global_source_registry_refresh() -> dict:
    """刷新官方源种子和逐国覆盖矩阵，不直接创建 verified 记录。"""
    logger.info("⏰ [调度] 开始刷新全球官方源注册表")
    from scripts.refresh_country_source_coverage import refresh as refresh_coverage
    from scripts.seed_country_research_outcomes import seed as seed_research_outcomes
    from scripts.seed_full_country_catalog import seed as seed_country_catalog
    from scripts.seed_global_official_sources import seed as seed_global_sources

    country_catalog = seed_country_catalog()
    inserted, updated = seed_global_sources()
    research_outcomes = seed_research_outcomes()
    coverage = refresh_coverage()
    result = {
        "country_catalog": country_catalog,
        "official_sources_inserted": inserted,
        "official_sources_updated": updated,
        "research_outcomes_updated": research_outcomes,
        "coverage": coverage,
    }
    logger.info("⏰ [调度] 全球官方源注册表刷新完成: %s", result)
    return result


def job_key_regulation_countdown_refresh() -> dict:
    """每日刷新关键法规分阶段适用节点，供倒计时、看板和飞书预警使用。"""
    logger.info("⏰ [调度] 开始刷新关键法规适用节点倒计时")
    try:
        result = ComplianceLifecycleRepository.seed_key_regulation_milestones()
        logger.info("⏰ [调度] 关键法规适用节点倒计时刷新完成: %s", result)
        return result
    except Exception as exc:
        logger.error("⏰ [调度] 关键法规适用节点倒计时刷新失败: %s", exc, exc_info=True)
        return {"status": "failed", "error": str(exc)}


def job_weekly_ai_discovery(limit_countries: int = WEEKLY_AI_DISCOVERY_LIMIT_COUNTRIES) -> dict:
    """每周受控 AI 发现：只生成和校验官方候选 source_records，不直接 verified。"""
    logger.info("⏰ [调度] 开始每周 AI 官方候选发现")
    try:
        from collector.discovery.service import get_ai_discovery_service

        result = get_ai_discovery_service().run(
            priorities=WEEKLY_AI_DISCOVERY_PRIORITIES,
            limit_countries=limit_countries,
            queries_per_country=WEEKLY_AI_DISCOVERY_QUERIES_PER_COUNTRY,
            validation_mode="ai",
        )
        logger.info("⏰ [调度] 每周 AI 官方候选发现完成: %s", result)
        return result
    except Exception as exc:
        logger.error("⏰ [调度] 每周 AI 官方候选发现失败: %s", exc, exc_info=True)
        return {
            "status": "failed",
            "candidate_count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "error": str(exc),
        }


def job_daily_ai_discovery(limit_countries: int = WEEKLY_AI_DISCOVERY_LIMIT_COUNTRIES) -> dict:
    """Compatibility wrapper; scheduled AI discovery now runs weekly."""
    return job_weekly_ai_discovery(limit_countries=limit_countries)


def job_weekly_compliance_update() -> dict:
    """每两周官方证据驱动更新闭环：源注册、发现、抓原文、分桶、解析、刷新、发报告。"""
    logger.info("⏰ [调度] 开始每两周全球合规知识库更新闭环")
    from collector.workflow.evidence_pipeline import EvidencePipelineRunner

    registry_result = job_global_source_registry_refresh()
    ai_discovery_result = {
        "status": "scheduled_separately",
        "cadence_days": 7,
        "job_id": "weekly_ai_discovery",
    }
    runner = EvidencePipelineRunner(
        source_sync=lambda priorities: get_official_source_pipeline().sync_country_priorities(list(priorities)),
        artifact_fetch=job_official_artifact_fetch,
        review_bucket=job_candidate_verification,
        document_parse=job_document_parse,
        spec_generate=job_spec_generate,
        read_model_refresh=job_read_model_refresh,
        weekly_report=job_weekly_report,
    )
    result = runner.run_weekly_closed_loop()
    result["source_collection"]["source_registry_refresh"] = registry_result
    result["source_collection"]["ai_discovery"] = ai_discovery_result
    logger.info("⏰ [调度] 每两周全球合规知识库更新闭环完成: %s", result)
    return result


def job_alert_scan() -> None:
    """预警扫描任务"""
    logger.info("⏰ [调度] 开始预警扫描")
    try:
        from notifier.alert_scanner import AlertScanner
        scanner = AlertScanner()
        result = scanner.run()
        logger.info("⏰ [调度] 预警扫描完成: %s", result)
    except Exception as e:
        logger.error("⏰ [调度] 预警扫描失败: %s", e, exc_info=True)
        raise


def job_frontline_feishu_digest() -> dict:
    """手动生成网安合规摘要；默认不再每日自动推送。"""
    logger.info("⏰ [手动] 开始网安合规摘要")
    try:
        from notifier.alert_scanner import AlertScanner
        scanner = AlertScanner()
        sent = scanner.scan_frontline_digest(lookback_hours=_hours_since_local_midnight())
        result = {"sent": bool(sent), "count": sent}
        logger.info("⏰ [手动] 网安合规摘要完成: %s", result)
        return result
    except Exception as e:
        logger.error("⏰ [手动] 网安合规摘要失败: %s", e, exc_info=True)
        raise


def _hours_since_local_midnight(now: datetime | None = None) -> int:
    now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    local_now = now.astimezone(ZoneInfo("Asia/Shanghai"))
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int(ceil((local_now - midnight).total_seconds() / 3600)))


def job_weekly_report() -> dict:
    """周报生成 + 飞书发送任务"""
    logger.info("⏰ [调度] 开始生成周报")
    try:
        from reporter.excel_reporter import ExcelReporter
        from notifier.feishu import get_notifier
        import tempfile, os

        settings = get_settings()

        # 生成 Excel
        reporter = ExcelReporter()
        report_date = datetime.now(timezone.utc).strftime("%Y%m%d")
        filename = f"cybersec_compliance_{report_date}.xlsx"

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name

        content = reporter.generate(output_path=tmp_path)

        # 上传 COS（如已配置）
        cos_url = None
        if settings.cos.secret_id:
            try:
                cos_url = _upload_to_cos(tmp_path, filename, settings)
            except Exception as e:
                logger.warning("COS 上传失败: %s", e)

        os.unlink(tmp_path)

        stats = _collect_weekly_report_stats()

        # 发飞书
        notifier = get_notifier()
        feishu_sent = False
        if notifier:
            feishu_sent = notifier.send_weekly_report_card(
                total_records=stats["total_records"],
                country_count=stats["country_count"],
                candidate_this_week=stats["candidate_this_week"],
                verified_this_week=stats["verified_this_week"],
                source_artifacts_this_week=stats["source_artifacts_this_week"],
                quarantined_this_week=stats["quarantined_this_week"],
                upcoming_alerts=stats["upcoming_alerts"],
                report_url=cos_url,
            )

        # 记录到 report_records 表
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO report_records
                        (report_type, report_date, file_name, cos_url, feishu_sent, feishu_sent_at, stats)
                    VALUES ('weekly', CURRENT_DATE, %s, %s, %s, NOW(), %s)
                    """,
                    (filename, cos_url, feishu_sent, json.dumps(stats, ensure_ascii=False, default=str)),
                )

        logger.info("⏰ [调度] 周报生成完成 [COS=%s]", cos_url or "未上传")
        return {"sent": feishu_sent, "cos_url": cos_url, "file_name": filename}

    except Exception as e:
        logger.error("⏰ [调度] 周报生成失败: %s", e, exc_info=True)
        raise


def _collect_weekly_report_stats() -> dict:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM compliance_index
            WHERE status='active' AND authenticity_status='verified'
            """
        )
        total = cur.fetchone()["total"]

        cur.execute(
            """
            SELECT COUNT(DISTINCT country_code) AS cnt
            FROM compliance_index
            WHERE status='active' AND authenticity_status='verified'
            """
        )
        country_cnt = cur.fetchone()["cnt"]

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM source_records
            WHERE source_status='candidate'
              AND created_at >= NOW() - INTERVAL '7 days'
            """
        )
        candidate_cnt = cur.fetchone()["cnt"]

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM review_cases
            WHERE current_status='verified'
              AND checked_at >= NOW() - INTERVAL '7 days'
            """
        )
        verified_cnt = cur.fetchone()["cnt"]

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM review_cases
            WHERE current_status='quarantined'
              AND checked_at >= NOW() - INTERVAL '7 days'
            """
        )
        quarantined_cnt = cur.fetchone()["cnt"]

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM source_artifacts
            WHERE download_status='downloaded'
              AND downloaded_at >= NOW() - INTERVAL '7 days'
            """
        )
        artifact_cnt = cur.fetchone()["cnt"]

        upcoming = ComplianceLifecycleRepository.get_upcoming_milestones(days=30, limit=10)

    return {
        "total_records": total,
        "country_count": country_cnt,
        "candidate_this_week": candidate_cnt,
        "verified_this_week": verified_cnt,
        "quarantined_this_week": quarantined_cnt,
        "source_artifacts_this_week": artifact_cnt,
        "upcoming_alerts": upcoming,
    }


def _upload_to_cos(local_path: str, filename: str, settings) -> str:
    """上传文件到腾讯云 COS，返回下载 URL"""
    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(
        Region=settings.cos.region,
        SecretId=settings.cos.secret_id,
        SecretKey=settings.cos.secret_key,
    )
    client = CosS3Client(config)
    key = f"{settings.cos.report_prefix}{filename}"
    with open(local_path, "rb") as f:
        client.put_object(Bucket=settings.cos.bucket, Body=f, Key=key)
    return f"https://{settings.cos.bucket}.cos.{settings.cos.region}.myqcloud.com/{key}"


# ============================================================
# 调度器配置
# ============================================================

def build_scheduler() -> BlockingScheduler:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    settings = get_settings()
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")

    # 全球官方源：每天凌晨1点；作为日报的确定性主来源
    scheduler.add_job(
        job_official_source_sync_daily,
        CronTrigger.from_crontab("0 1 * * *", timezone="Asia/Shanghai"),
        id="official_source_sync_daily",
        name="全球官方源同步",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 每两周完整更新闭环：官方源、原文、审核分桶、解析、读模型、Excel与飞书
    scheduler.add_job(
        job_weekly_compliance_update,
        IntervalTrigger(weeks=2, start_date=BIWEEKLY_UPDATE_START, timezone="Asia/Shanghai"),
        id="weekly_compliance_update",
        name="每两周全球合规知识库更新",
        max_instances=1,
        misfire_grace_time=7200,
    )

    # 关键法规倒计时：每天刷新 CRA 等分阶段适用节点，确保看板/飞书窗口准确
    scheduler.add_job(
        job_key_regulation_countdown_refresh,
        CronTrigger.from_crontab("5 0 * * *", timezone="Asia/Shanghai"),
        id="key_regulation_countdown_refresh",
        name="关键法规适用节点倒计时刷新",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # AI 发现：每周一凌晨0点30，只产生官方候选线索和待审核证据，不直接写正式库
    scheduler.add_job(
        job_weekly_ai_discovery,
        CronTrigger.from_crontab(WEEKLY_AI_DISCOVERY_CRON, timezone="Asia/Shanghai"),
        id="weekly_ai_discovery",
        name="每周AI官方候选发现",
        max_instances=1,
        misfire_grace_time=7200,
    )

    # 原文工件抓取：每天凌晨2点30
    scheduler.add_job(
        job_official_artifact_fetch,
        CronTrigger.from_crontab("30 2 * * *", timezone="Asia/Shanghai"),
        id="official_artifact_fetch",
        name="官方原文抓取",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 候选验真：每天凌晨3点
    scheduler.add_job(
        job_candidate_verification,
        CronTrigger.from_crontab("0 3 * * *", timezone="Asia/Shanghai"),
        id="candidate_verification",
        name="候选规则验真",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 文档解析：每天凌晨3点30分
    scheduler.add_job(
        job_document_parse,
        CronTrigger.from_crontab("30 3 * * *", timezone="Asia/Shanghai"),
        id="document_parse",
        name="官方原文解析",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 规格输出：只处理 verified 且已完成索引的官方原文
    scheduler.add_job(
        job_spec_generate,
        CronTrigger.from_crontab("45 3 * * *", timezone="Asia/Shanghai"),
        id="spec_generate",
        name="verified原文规格输出",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 预警扫描：每天凌晨4点
    scheduler.add_job(
        job_alert_scan,
        CronTrigger.from_crontab("0 4 * * *", timezone="Asia/Shanghai"),
        id="alert_scan",
        name="预警扫描",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 覆盖矩阵刷新：每天凌晨4点30，仅统计，不改变真实性状态
    scheduler.add_job(
        job_global_source_registry_refresh,
        CronTrigger.from_crontab("30 4 * * *", timezone="Asia/Shanghai"),
        id="source_registry_refresh",
        name="全球官方源覆盖矩阵刷新",
        max_instances=1,
        misfire_grace_time=3600,
    )

    return scheduler


def _on_job_error(event) -> None:
    logger.error("❌ 任务 [%s] 执行失败: %s", event.job_id, event.exception)


def _on_job_executed(event) -> None:
    retval = getattr(event, "retval", None)
    if isinstance(retval, (int, float)):
        logger.info("✅ 任务 [%s] 执行完成，返回值: %.1f", event.job_id, float(retval))
    elif retval is None:
        logger.info("✅ 任务 [%s] 执行完成", event.job_id)
    else:
        logger.info("✅ 任务 [%s] 执行完成，返回: %s", event.job_id, retval)


def main() -> None:
    from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

    logger.info("=" * 60)
    logger.info("  网安合规助手 - 调度器启动")
    logger.info("=" * 60)

    db_health = health_check()
    if db_health["status"] != "healthy":
        logger.critical("❌ 数据库不可用，调度器退出")
        sys.exit(1)
    logger.info("✅ 数据库健康")

    scheduler = build_scheduler()
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)

    # 打印任务列表
    logger.info("已配置任务：")
    for job in scheduler.get_jobs():
        logger.info("  • [%s] %s", job.id, job.trigger)

    # 优雅退出
    def _shutdown(signum, frame):
        logger.info("收到信号 %s，正在优雅退出...", signum)
        scheduler.shutdown(wait=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("调度器运行中（Ctrl+C 退出）")
    scheduler.start()


if __name__ == "__main__":
    main()
