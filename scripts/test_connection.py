#!/usr/bin/env python3
"""
scripts/test_connection.py
部署后第一步：测试所有依赖的连通性

用法: python scripts/test_connection.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import setup_logging

setup_logging(level="INFO")

import logging
logger = logging.getLogger(__name__)


def test_database() -> bool:
    logger.info("--- 测试数据库连接 ---")
    try:
        from database.connection import health_check, get_cursor
        result = health_check()
        if result["status"] == "healthy":
            logger.info("✅ 数据库连接正常: %s", result.get("version", "")[:40])
            with get_cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM countries")
                cnt = cur.fetchone()["cnt"]
                logger.info("   国家/地区记录: %d 条", cnt)
                cur.execute(
                    """
                    SELECT CASE
                        WHEN to_regclass('public.compliance_index') IS NULL THEN 0
                        ELSE (SELECT COUNT(*) FROM compliance_index WHERE authenticity_status='verified')
                    END AS cnt
                    """
                )
                cnt = cur.fetchone()["cnt"]
                logger.info("   verified 合规读模型: %d 条", cnt)
            return True
        else:
            logger.error("❌ 数据库不健康: %s", result)
            return False
    except Exception as e:
        logger.error("❌ 数据库连接失败: %s", e)
        return False


def test_volcengine() -> bool:
    logger.info("--- 测试火山引擎 API ---")
    try:
        from config.settings import get_settings
        settings = get_settings()
        if not settings.volcengine.api_key:
            logger.warning("⚠️  火山引擎 API Key 未配置，跳过")
            return False

        from collector.providers.volcengine import create_volcengine_providers
        providers = create_volcengine_providers(
            api_key=settings.volcengine.api_key,
            base_url=settings.volcengine.base_url,
            primary_model=settings.volcengine.model_primary,
        )
        provider = providers[0]

        resp = provider.chat(
            messages=[
                {"role": "user", "content": "请用一句话介绍欧盟CRA法规，不超过50字。"}
            ],
            temperature=0.1,
            max_tokens=100,
            enable_web_search=False,  # 连通测试不用联网
        )
        logger.info("✅ 火山引擎 API 正常 [%s]", settings.volcengine.model_primary)
        logger.info("   响应: %s", resp.content[:100])
        logger.info("   延迟: %.0fms | tokens: %d", resp.latency_ms, resp.completion_tokens)
        return True
    except Exception as e:
        logger.error("❌ 火山引擎 API 失败: %s", e)
        return False


def test_volcengine_web_search() -> bool:
    logger.info("--- 测试火山引擎联网搜索 ---")
    try:
        from config.settings import get_settings
        settings = get_settings()
        if not settings.volcengine.api_key:
            return False

        from collector.providers.volcengine import create_volcengine_providers
        providers = create_volcengine_providers(
            api_key=settings.volcengine.api_key,
            base_url=settings.volcengine.base_url,
            primary_model=settings.volcengine.model_primary,
        )
        provider = providers[0]

        resp = provider.chat(
            messages=[
                {"role": "user", "content": "搜索欧盟CRA法规最新生效日期，只需回答日期，不超过20字。"}
            ],
            temperature=0.1,
            max_tokens=100,
            enable_web_search=True,
        )
        logger.info("✅ 联网搜索正常")
        logger.info("   响应: %s", resp.content[:150])
        logger.info("   联网搜索使用: %s", resp.web_search_used)
        return True
    except Exception as e:
        logger.error("❌ 联网搜索失败: %s", e)
        return False


def test_feishu() -> bool:
    logger.info("--- 测试飞书 Webhook ---")
    try:
        from config.settings import get_settings
        settings = get_settings()
        if not settings.feishu.webhook_url:
            logger.warning("⚠️  飞书 Webhook 未配置，跳过")
            return False

        from notifier.feishu import FeishuNotifier
        notifier = FeishuNotifier(
            webhook_url=settings.feishu.webhook_url,
            secret=settings.feishu.webhook_secret,
        )
        ok = notifier.send_text("✅ 网安合规助手部署测试 - 飞书通知正常")
        if ok:
            logger.info("✅ 飞书 Webhook 发送成功，请检查群消息")
        else:
            logger.error("❌ 飞书 Webhook 发送失败")
        return ok
    except Exception as e:
        logger.error("❌ 飞书 Webhook 测试失败: %s", e)
        return False


def main():
    results = {}

    logger.info("=" * 60)
    logger.info("  网安合规助手 - 连通性测试")
    logger.info("=" * 60)

    results["database"] = test_database()
    results["volcengine_api"] = test_volcengine()
    results["volcengine_search"] = test_volcengine_web_search()
    results["feishu"] = test_feishu()

    logger.info("")
    logger.info("=" * 60)
    logger.info("  测试结果汇总")
    logger.info("=" * 60)
    all_pass = True
    for name, ok in results.items():
        icon = "✅" if ok else ("⚠️ " if name == "feishu" else "❌")
        logger.info("  %s %s", icon, name)
        if not ok and name in ("database", "volcengine_api"):
            all_pass = False

    if all_pass:
        logger.info("")
        logger.info("🎉 核心依赖测试通过！下一步可以启动后台和调度器:")
        logger.info("   uvicorn admin.api.main:app --host 0.0.0.0 --port 8080")
        logger.info("   python scheduler/main.py")
        logger.info("也可以在后台 Tasks 页面触发“每周完整更新”。")
    else:
        logger.info("")
        logger.info("❌ 存在失败项，请检查 config/.env 配置")
        sys.exit(1)


if __name__ == "__main__":
    main()
