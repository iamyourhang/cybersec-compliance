#!/usr/bin/env python3
"""
scripts/run_full_update.py
旧全量更新脚本。

默认拒绝执行，避免重新走 AI 搜索直写正式库的旧链路。
只有显式传入 --legacy-unsafe 时才允许运行。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import setup_logging
from config.settings import get_settings
from database.connection import get_connection, health_check
from collector.providers.factory import build_provider_manager
from collector.engine import CollectorEngine

setup_logging(level="INFO")
logger = logging.getLogger(__name__)


def ensure_legacy_opt_in(enabled: bool) -> None:
    if enabled:
        return
    print(
        "❌ scripts/run_full_update.py 已默认禁用：它会重走旧 CollectorEngine AI 搜索更新链路。\n"
        "请改用官方源同步任务；如确需临时排障，请显式传入 --legacy-unsafe。",
        file=sys.stderr,
    )
    raise SystemExit(2)


def record_task(task_type: str, status: str, stats: dict, triggered_by: str = "manual") -> None:
    """将任务记录写入 update_tasks 表"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO update_tasks
                        (task_type, status, finished_at, total_records,
                         created_count, updated_count, error_count,
                         error_details, triggered_by)
                    VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        task_type,
                        status,
                        stats.get("total", 0),
                        stats.get("created", 0),
                        stats.get("updated", 0),
                        stats.get("errors", 0),
                        json.dumps(stats.get("error_list", [])[:20]),
                        triggered_by,
                    ),
                )
    except Exception as e:
        logger.error("记录任务状态失败: %s", e)


def main() -> None:
    parser = argparse.ArgumentParser(description="全量更新网安合规知识库")
    parser.add_argument("--countries", nargs="+", help="指定国家代码，如 EU US GB")
    parser.add_argument("--priority", choices=["P1", "P2", "P3"], help="按优先级筛选国家")
    parser.add_argument("--dry-run", action="store_true", help="只打印 Prompt，不实际调用 AI 和写库")
    parser.add_argument("--legacy-unsafe", action="store_true", help="显式确认运行旧全量更新脚本（不推荐）")
    args = parser.parse_args()
    ensure_legacy_opt_in(args.legacy_unsafe)

    settings = get_settings()

    logger.info("=" * 70)
    logger.info("  网安合规助手 - 全量更新")
    logger.info("  时间: %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    logger.info("=" * 70)

    # 数据库健康检查
    db_health = health_check()
    if db_health["status"] != "healthy":
        logger.critical("❌ 数据库不可用: %s", db_health)
        sys.exit(1)
    logger.info("✅ 数据库连接正常")

    if args.dry_run:
        logger.info("⚠️  DRY RUN 模式，不实际调用 AI")
        from collector.parsers.prompts import build_country_scan_prompt, SYSTEM_PROMPT
        from database.connection import get_cursor
        with get_cursor() as cur:
            cur.execute(
                "SELECT code, name_zh FROM countries WHERE enabled=TRUE ORDER BY priority LIMIT 2"
            )
            countries = cur.fetchall()
        for c in countries:
            prompt = build_country_scan_prompt(
                country_code=c["code"],
                country_name=c["name_zh"],
                product_types=["enterprise_router", "home_router"],
                existing_names=[],
            )
            print(f"\n{'='*60}\nSYSTEM:\n{SYSTEM_PROMPT[:200]}...\n\nUSER [{c['code']}]:\n{prompt[:500]}...")
        return

    # 按优先级过滤国家
    country_codes = args.countries
    if args.priority and not country_codes:
        from database.connection import get_cursor
        with get_cursor() as cur:
            cur.execute(
                "SELECT code FROM countries WHERE priority=%s AND enabled=TRUE",
                (args.priority,),
            )
            country_codes = [r["code"] for r in cur.fetchall()]
        logger.info("按优先级 %s 筛选，共 %d 个国家", args.priority, len(country_codes))

    # 构建 Provider Manager
    logger.info("正在初始化 AI Provider...")
    try:
        pm = build_provider_manager()
    except RuntimeError as e:
        logger.critical("❌ %s", e)
        sys.exit(1)

    # 执行全量更新
    engine = CollectorEngine(pm)
    try:
        stats = engine.full_update(country_codes=country_codes)
        status = "success" if stats.error_count == 0 else "partial"
        record_task(
            task_type="full_update",
            status=status,
            stats={
                "total": stats.created_count + stats.updated_count + stats.skipped_count,
                "created": stats.created_count,
                "updated": stats.updated_count,
                "errors": stats.error_count,
                "error_list": stats.errors,
            },
        )
        logger.info("\n%s", stats.summary())
        sys.exit(0 if status == "success" else 1)

    except KeyboardInterrupt:
        logger.warning("用户中断")
        sys.exit(130)
    except Exception as e:
        logger.critical("全量更新异常终止: %s", e, exc_info=True)
        record_task("full_update", "failed", {"errors": 1, "error_list": [str(e)]})
        sys.exit(1)


if __name__ == "__main__":
    main()
