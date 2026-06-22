"""
feishu_bot/query_handler.py
查询处理器 - 根据意图查询数据库，返回结果
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from collector.document.rag_service import AskPayload, RAGService
from collector.query.service import get_compliance_query_service
from database.connection import get_cursor
from database.repository import ComplianceLifecycleRepository

logger = logging.getLogger(__name__)

# 产品代码 → 中文名
PRODUCT_NAMES = {
    "enterprise_router": "企业级路由器",
    "home_router": "家用路由器",
    "switch": "网络交换机",
    "firewall_utm": "防火墙/UTM",
    "wireless_ap": "无线AP",
    "industrial_gateway": "工业网关",
    "sd_wan": "SD-WAN",
    "security_gateway": "网络安全网关",
    "cloud_desktop": "云桌面",
    "software": "软件",
}


def query_compliance(
    product_code: str,
    country_code: str,
    mandatory_only: bool = False,
) -> Dict[str, Any]:
    """查询某产品出口到某国的合规要求"""
    result = get_compliance_query_service().query_compliance(
        product_code=product_code,
        country_code=country_code,
        mandatory_only=mandatory_only,
    )
    result["product_name"] = PRODUCT_NAMES.get(product_code, product_code)
    return result


def query_regulation(keyword: str, country_code: Optional[str] = None) -> List[Dict]:
    """按关键词搜索法规信息"""
    return get_compliance_query_service().query_regulation(keyword=keyword, country_code=country_code)


def query_upcoming(days: int = 30) -> List[Dict]:
    """查询即将生效的 verified 法规/认证。

    飞书属于对外交付面，不能继续依赖旧的 v_upcoming_effective 视图；
    该视图历史上来自 compliance_knowledge，可能混入 suspicious/quarantined。
    """
    rows = ComplianceLifecycleRepository.get_upcoming_milestones(days=days, limit=20)
    for r in rows:
        if r.get("effective_date"):
            r["effective_date"] = str(r["effective_date"])
        if r.get("milestone_date"):
            r["milestone_date"] = str(r["milestone_date"])
    return rows


def query_all_by_country(country_code: str) -> dict:
    """查询某国所有合规要求（不限产品）"""
    result = get_compliance_query_service().query_all_by_country(country_code=country_code)
    result["product_name"] = "所有产品"
    return result


def query_rag(
    question: str,
    country_code: Optional[str] = None,
    product_code: Optional[str] = None,
    document_id: Optional[str] = None,
) -> Dict[str, Any]:
    service = RAGService()
    return service.ask(
        AskPayload(
            question=question,
            country_code=country_code,
            product_code=product_code,
            document_id=document_id,
            top_k=6,
        )
    )
