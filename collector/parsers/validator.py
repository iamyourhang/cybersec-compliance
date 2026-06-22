"""
collector/parsers/validator.py
合规数据入库前验证器 - 过滤明显不相关或低质量数据
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# 明确排除的关键词（出现在名称中直接拒绝）
EXCLUDE_KEYWORDS = [
    "ISO 9001", "ISO 14001", "ISO 45001",
    "RoHS", "WEEE", "ErP", "Energy Star",
    "CE marking", "CE-LVD", "CB Scheme",
    "REACH", "conflict mineral",
    # NIST SP 800系列 - IT系统控制框架，不是网络设备认证
    "NIST SP 800-53", "NIST Special Publication 800-53",
    "NIST SP 800-171", "NIST Special Publication 800-171",
    "NIST SP 800-82", "NIST Special Publication 800-82",
    "SOC 2", "SOC2",
    "PCI DSS", "HIPAA",
    "FCC Part 15",      # 射频，不是网络安全
    "SRRC", "ISED",
]

# 过于通用的名称模式（P2/P3国家低置信度时拒绝）
GENERIC_NAME_PATTERNS = [
    "Network Security Equipment Compliance Regulation",
    "Cybersecurity Equipment Compliance",
    "Network Device Security Regulation",
    "ICT Equipment Cybersecurity Regulation",
    "Network Equipment Security Standard",
]

# 可信的认证/法规发布机构关键词（认证类条目必须包含其一）
TRUSTED_BODIES_KEYWORDS = [
    # 欧盟
    "ENISA", "European Commission", "European Parliament",
    "BSI", "ANSSI", "NCSC", "NLNCSA",
    # 美国
    "FCC", "NIST", "CISA", "NSA",
    # 英国
    "DCMS", "OPSS", "NCSC",
    # 中国
    "CCRC", "MIIT", "CAC", "公安部", "工信部",
    # 日本
    "MIC", "METI", "IPA", "NICT", "総務省",
    # 韩国
    "KISA", "MSIT", "NIS",
    # 国际标准组织
    "ETSI", "IEC", "ISO", "ITU", "IEEE",
    # 各国监管机构
    "IMDA", "ACMA", "ISED Canada", "ANATEL",
    "TÜV", "UL", "SGS", "Bureau Veritas",
]

# AI容易编造的模式（名称包含这些模式且issuing_body不可信时拒绝）
SUSPICIOUS_PATTERNS = [
    "Voluntary Cybersecurity Label for",
    "Cybersecurity Certification Scheme for",
    "Voluntary Small and Medium",
    "Secure Home Network Device Certification",
    "Trust Mark Certification",
    # EU 细分产品认证（EU只有EUCC/EUCS等通用方案，没有按产品细分的认证）
    "EU Consumer Router Cybersecurity",
    "EU Enterprise Networking Equipment Cybersecurity Certification",
    "EU SD-WAN Cybersecurity Certification",
    "EU Industrial Gateway Cybersecurity Certification",
    "EU Consumer IoT Cybersecurity Certification",
    # 韩国AI编造的细分认证（真实存在的只有CC/ISMS-P/K-IoT）
    "Korea AI-Embedded",
    "Korea Edge Computing Network",
    "Korea Software Security Certification",
    "Korea Zero Trust Network Equipment Security Certification",
    "Korea 5G Network Equipment Security Certification",
    "Korea Critical Infrastructure Network Equipment",
    "Zero Trust Network Equipment Security Compliance Regulation",
]

# 真实存在的韩国认证白名单
KR_WHITELIST = [
    "ISMS-P", "K-IoT", "Korea Common Criteria", "K-CC",
    "KS X 3260", "KS X 3265", "KS X 3267", "KS X 3268", "KS X 3269",
    "Act on the Development of Internet of Things",
    "Act on the Protection of Information and Communications",
    "Information Security Management System",
]

# 真实存在的认证白名单（即使匹配可疑模式也放行）
WHITELIST_NAMES = [
    "EUCC",
    "EUCS",
    "EU Cybersecurity Act",
    "EU Cyber Resilience Act",
    "FCC Cyber Trust Mark",
    "UK Cyber Essentials",
    "等保",
    "ISMS-P",
    "NOTICE",
]


def validate_entry(entry: Dict[str, Any]) -> Tuple[bool, str]:
    """
    验证单条合规记录是否应该入库。
    返回 (是否通过, 拒绝原因)
    """
    name = entry.get("name", "")
    entry_type = entry.get("entry_type", "")
    issuing_body = entry.get("issuing_body", "") or ""
    confidence = entry.get("confidence_score", 100)
    country = entry.get("country_code", "")

    # 1. 排除关键词检查
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in name.lower():
            return False, f"包含排除关键词: {kw}"

    # 2. 认证类条目额外验证
    if entry_type == "certification":
        # 置信度低于75的认证直接拒绝
        if confidence < 75:
            return False, f"认证置信度过低: {confidence}"

        # 检查发布机构是否可信
        body_trusted = any(
            kw.lower() in issuing_body.lower()
            for kw in TRUSTED_BODIES_KEYWORDS
        )

        # 白名单直接放行
        is_whitelisted = any(
            wl.lower() in name.lower() for wl in WHITELIST_NAMES
        )
        # 韩国认证白名单
        if country == 'KR' and any(wl.lower() in name.lower() for wl in KR_WHITELIST):
            return True, ""
        if is_whitelisted:
            return True, ""
        # 韩国认证：不在白名单内的认证类条目，置信度必须>=95
        if country == 'KR' and entry_type == 'certification' and confidence < 95:
            if not any(wl.lower() in name.lower() for wl in KR_WHITELIST):
                return False, f"韩国认证不在白名单且置信度不足: {name[:50]}"

        # 检查是否有可疑编造模式
        is_suspicious = any(
            pattern.lower() in name.lower()
            for pattern in SUSPICIOUS_PATTERNS
        )

        # 可疑模式 + 不可信机构 = 拒绝
        if is_suspicious and not body_trusted:
            return False, f"疑似AI编造的认证: {name[:60]}"

        # P3国家的认证，置信度低于85且有可疑模式则拒绝
        if country not in ("EU", "US", "GB", "CN", "JP", "KR", "SG", "AU", "CA"):
            if confidence < 85 and is_suspicious:
                return False, f"P2/P3国家低置信度可疑认证"

    # 3. 标准类条目：必须是真实国际标准
    if entry_type == "standard":
        # NIST SP 800系列是IT系统框架，不是网络设备认证标准
        if "NIST SP 800" in name and "FIPS" not in name:
            return False, "NIST SP 800系列是IT系统框架，非网络设备认证"

    # 4. 过于通用的名称 + P2/P3国家 + 低置信度 = 拒绝
    if country not in ("EU","US","GB","CN","JP","KR","SG","AU","CA","IN","DE","FR","NL","KR"):
        is_generic = any(pattern.lower() in name.lower() for pattern in GENERIC_NAME_PATTERNS)
        if is_generic and confidence < 88:
            return False, f"过于通用的名称，疑似AI编造: {name[:50]}"

    # 5. 通过验证
    return True, ""


def filter_entries(
    entries: List[Dict[str, Any]],
    source: str = "",
) -> Tuple[List[Dict], List[Dict]]:
    """
    过滤条目列表。
    返回 (通过的条目列表, 被拒绝的条目列表)
    """
    passed = []
    rejected = []

    for entry in entries:
        ok, reason = validate_entry(entry)
        if ok:
            passed.append(entry)
        else:
            rejected.append({**entry, "_reject_reason": reason})
            logger.info(
                "  🚫 过滤: [%s] %s — %s",
                entry.get("country_code", "?"),
                entry.get("name", "?")[:60],
                reason,
            )

    if rejected:
        logger.info(
            "  过滤结果: 通过 %d 条，拒绝 %d 条 [来源: %s]",
            len(passed), len(rejected), source,
        )

    return passed, rejected
