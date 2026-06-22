"""
collector/parsers/compliance_parser.py
解析 AI 返回的合规数据，健壮处理各种格式异常
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# 合法产品代码集合
VALID_PRODUCTS = {
    "enterprise_router", "home_router", "switch", "firewall_utm",
    "wireless_ap", "industrial_gateway", "sd_wan", "security_gateway",
    "cloud_desktop", "software",
}

VALID_ENTRY_TYPES = {"regulation", "standard", "certification"}
ENTRY_TYPE_ALIASES = {
    "guidance": "standard",
    "guide": "standard",
    "policy": "standard",
    "strategy": "standard",
    "strategy_plan": "standard",
}
VALID_MANDATORY = {"mandatory", "voluntary", "recommended"}
VALID_STATUS = {"active", "deprecated", "draft", "superseded"}

# 必须字段
REQUIRED_FIELDS = {"name", "entry_type", "mandatory", "country_code"}


class ParseError(Exception):
    """解析失败异常"""


def extract_json_from_text(text: str) -> str:
    """
    从 LLM 输出中提取 JSON 内容。
    处理：markdown 代码块、前后多余文字、多余注释等。
    """
    if not text or not text.strip():
        raise ParseError("AI 返回内容为空")

    # 移除 markdown 代码块标记
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # 尝试找到 JSON 数组或对象的起止位置
    # 优先找数组
    array_match = re.search(r"\[[\s\S]*\]", text)
    object_match = re.search(r"\{[\s\S]*\}", text)

    if array_match and object_match:
        # 取最先出现的那个
        if array_match.start() < object_match.start():
            return array_match.group(0)
        else:
            return object_match.group(0)
    elif array_match:
        return array_match.group(0)
    elif object_match:
        return object_match.group(0)

    raise ParseError(f"无法从输出中提取 JSON，原始内容（前200字）: {text[:200]}")


def parse_date(value: Any) -> Optional[date]:
    """安全解析日期字段，支持多种格式"""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "n/a", "tbd", "待定", "暂定"):
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    logger.warning("无法解析日期: %s", s)
    return None


def normalize_entry(raw: Dict[str, Any], source_name: str = "ai") -> Dict[str, Any]:
    """
    规范化单条合规记录：
    - 清洗枚举字段
    - 规范化日期
    - 过滤非法产品代码
    - 确保必填字段存在
    """
    entry: Dict[str, Any] = {}

    # 字符串字段
    for field in ["name", "name_local", "country_code", "issuing_body",
                  "region_scope", "scope_description", "assessment_procedure",
                  "official_url", "official_url_backup", "remarks",
                  "validity_period"]:
        val = raw.get(field)
        entry[field] = str(val).strip() if val and str(val).strip() not in ("null", "None") else None

    # name 必填
    if not entry.get("name"):
        raise ParseError(f"记录缺少必填字段 'name': {raw}")

    # country_code 必填且大写
    if entry.get("country_code"):
        entry["country_code"] = entry["country_code"].upper()
    else:
        raise ParseError(f"记录缺少必填字段 'country_code': {raw.get('name')}")

    # 枚举字段
    entry_type = str(raw.get("entry_type", "")).lower().strip()
    entry_type = ENTRY_TYPE_ALIASES.get(entry_type, entry_type)
    entry["entry_type"] = entry_type if entry_type in VALID_ENTRY_TYPES else "regulation"
    if entry_type not in VALID_ENTRY_TYPES:
        logger.warning("未知 entry_type '%s'，默认设为 regulation", entry_type)

    mandatory = str(raw.get("mandatory", "")).lower().strip()
    entry["mandatory"] = mandatory if mandatory in VALID_MANDATORY else "mandatory"

    status = str(raw.get("status", "")).lower().strip()
    entry["status"] = status if status in VALID_STATUS else "active"

    # 日期字段
    entry["effective_date"] = parse_date(raw.get("effective_date"))
    entry["transition_end_date"] = parse_date(raw.get("transition_end_date"))
    entry["published_date"] = parse_date(raw.get("published_date"))

    # 数组字段
    for arr_field in ["technical_standards", "regulation_basis", "testing_bodies"]:
        val = raw.get(arr_field)
        if isinstance(val, list):
            entry[arr_field] = [str(v).strip() for v in val if v and str(v).strip()]
        elif val and str(val).strip():
            entry[arr_field] = [str(val).strip()]
        else:
            entry[arr_field] = []

    # applicable_products：过滤非法值
    raw_products = raw.get("applicable_products", [])
    if isinstance(raw_products, list):
        valid_prods = [p for p in raw_products if p in VALID_PRODUCTS]
        invalid_prods = [p for p in raw_products if p not in VALID_PRODUCTS]
        if invalid_prods:
            logger.warning("过滤非法产品代码: %s", invalid_prods)
        entry["applicable_products"] = valid_prods
    else:
        entry["applicable_products"] = []

    # requirements (JSONB)
    req = raw.get("requirements")
    if isinstance(req, dict):
        entry["requirements"] = req
    elif isinstance(req, str) and req.strip():
        try:
            entry["requirements"] = json.loads(req)
        except json.JSONDecodeError:
            entry["requirements"] = {"raw": req}
    else:
        entry["requirements"] = None

    # 置信度分数
    try:
        entry["confidence_score"] = max(0, min(100, int(raw.get("confidence_score", 70))))
    except (ValueError, TypeError):
        entry["confidence_score"] = 70

    # 数据来源
    entry["data_source"] = source_name
    entry["verified"] = False

    return entry


def parse_single_entry(
    ai_output: str,
    source_name: str = "ai",
) -> Dict[str, Any]:
    """
    解析单条记录的 AI 输出。
    返回规范化后的记录字典。
    """
    json_str = extract_json_from_text(ai_output)
    try:
        raw = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ParseError(f"JSON 解析失败: {e}\n原始: {json_str[:500]}") from e

    if isinstance(raw, list):
        if not raw:
            raise ParseError("AI 返回了空列表")
        raw = raw[0]

    return normalize_entry(raw, source_name)


def parse_entry_list(
    ai_output: str,
    source_name: str = "ai",
    country_code: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    解析批量记录的 AI 输出。
    返回 (成功列表, 失败原因列表)
    """
    json_str = extract_json_from_text(ai_output)
    try:
        raw_list = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ParseError(f"JSON 解析失败: {e}") from e

    if isinstance(raw_list, dict):
        # 有时 AI 返回单个对象而不是数组
        raw_list = [raw_list]

    if not isinstance(raw_list, list):
        raise ParseError(f"期望 JSON 数组，得到: {type(raw_list)}")

    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    for i, raw in enumerate(raw_list):
        try:
            if not isinstance(raw, dict):
                errors.append(f"第{i}条：不是对象类型")
                continue
            # 如果 AI 没有填 country_code，用传入的补上
            if country_code and not raw.get("country_code"):
                raw["country_code"] = country_code
            entry = normalize_entry(raw, source_name)
            results.append(entry)
        except ParseError as e:
            errors.append(f"第{i}条解析失败: {e}")
            logger.warning("第%d条记录解析失败: %s | raw: %s", i, e, str(raw)[:200])

    logger.info("批量解析完成: 成功 %d 条，失败 %d 条", len(results), len(errors))
    return results, errors


def parse_incremental_check(ai_output: str) -> Dict[str, Any]:
    """
    解析增量检查结果。
    返回 {"has_changes": bool, "change_summary": str, "updated_fields": dict}
    """
    try:
        json_str = extract_json_from_text(ai_output)
        result = json.loads(json_str)
    except (ParseError, json.JSONDecodeError) as e:
        logger.warning("增量检查结果解析失败: %s", e)
        return {"has_changes": False, "change_summary": None, "updated_fields": {}}

    has_changes = bool(result.get("has_changes", False))
    updated_fields = result.get("updated_fields", {})

    # 规范化 updated_fields 中的日期
    for date_field in ["effective_date", "transition_end_date", "published_date"]:
        if date_field in updated_fields:
            parsed = parse_date(updated_fields[date_field])
            updated_fields[date_field] = str(parsed) if parsed else None

    return {
        "has_changes": has_changes,
        "change_summary": result.get("change_summary"),
        "updated_fields": updated_fields,
        "confidence_score": result.get("confidence_score", 70),
        "sources": result.get("sources", []),
    }
