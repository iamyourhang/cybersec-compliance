"""
collector/document/spec_compiler.py
法规规格编译器：从已入库的原文 chunk 中抽取可追溯条款证据，并编译成规格要求。

这个模块刻意不联网、不让模型自由发挥；它只把本地原文切片中已经出现的明确规则转换为
可落库的规格草案，确保每条规格至少带条款号、页码或 chunk id 之一。
"""
from __future__ import annotations

from dataclasses import dataclass
import uuid
from typing import Any, Dict, Iterable, List, Optional

from database.repository import RegulationChunkRepository


@dataclass(frozen=True)
class ClauseEvidence:
    rule_id: str
    clause_ref: str
    source_pages: Optional[str]
    source_chunk_ids: List[str]
    excerpt: str


def compile_rule_level_specs(
    doc_id: Optional[str],
    country_code: str,
    products: List[str],
) -> List[Dict[str, Any]]:
    if not doc_id:
        return []
    chunks = RegulationChunkRepository.list_by_document(doc_id, limit=5000)
    evidence = ClauseExtractor(chunks).extract()
    return SpecVerifier().filter_valid(RequirementCompiler(products).compile(evidence))


class ClauseExtractor:
    def __init__(self, chunks: Iterable[Dict[str, Any]]):
        self._chunks = list(chunks)

    def extract(self) -> List[ClauseEvidence]:
        evidence: List[ClauseEvidence] = []
        seen: set[tuple[str, str]] = set()
        for chunk in self._chunks:
            content = (chunk.get("content") or "")
            lowered = content.lower()
            source_pages = _format_source_pages(chunk)
            source_chunk_ids = _format_source_chunk_ids(chunk)
            for rule_id, clause_ref in self._detect_rules(lowered):
                key = (rule_id, ",".join(source_chunk_ids) or source_pages or clause_ref)
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(
                    ClauseEvidence(
                        rule_id=rule_id,
                        clause_ref=clause_ref,
                        source_pages=source_pages,
                        source_chunk_ids=source_chunk_ids,
                        excerpt=content[:1200],
                    )
                )
        return evidence

    def _detect_rules(self, lowered: str) -> List[tuple[str, str]]:
        rules: List[tuple[str, str]] = []
        if "article 3(3)" in lowered and ("point (d)" in lowered or "(d)" in lowered):
            rules.append(("NET-RED-001", "Article 3(3)(d)"))
        if "article 3(3)" in lowered and ("point (e)" in lowered or "(e)" in lowered):
            rules.append(("ENC-RED-001", "Article 3(3)(e)"))
        if "article 3(3)" in lowered and ("point (f)" in lowered or "(f)" in lowered):
            rules.append(("AUTH-RED-001", "Article 3(3)(f)"))
        if ("8.220(c)(3)" in lowered or "shall accept test data" in lowered) and (
            "cyberlab" in lowered or "test data" in lowered
        ):
            rules.append(("CMP-FCC-001", "§ 8.220(c)(3)"))
        if ("8.220(g)" in lowered or "post-market surveillance" in lowered) and (
            "post-market" in lowered or "surveillance" in lowered
        ):
            rules.append(("CMP-FCC-002", "§ 8.220(g)"))
        if (
            "8.222(b)" in lowered
            or "default password" in lowered
            or "minimum support period" in lowered
            or "sbom" in lowered
            or "software updates and patches" in lowered
        ) and (
            "registry" in lowered
            or "default password" in lowered
            or "secure updates" in lowered
            or "software updates" in lowered
            or "minimum support" in lowered
            or "sbom" in lowered
        ):
            rules.append(("UPD-FCC-001", "§ 8.222(b)"))
        if (
            "annex i" in lowered
            and "essential cybersecurity requirements" in lowered
            and "without known exploitable vulnerabilities" in lowered
        ):
            rules.append(("CFG-CRA-001", "Annex I Part I (2)(a)-(b)"))
        if "security updates" in lowered and (
            "automatic security updates" in lowered or "vulnerabilities can be addressed" in lowered
        ):
            rules.append(("UPD-CRA-001", "Annex I Part I (2)(c), Annex I Part II (2)"))
        if "software bill of materials" in lowered or "drawing up a software bill" in lowered:
            rules.append(("VUL-CRA-001", "Annex I Part II (1)"))
        if "article 14" in lowered and "actively exploited vulnerability" in lowered and "24 hours" in lowered:
            rules.append(("VUL-CRA-002", "Article 14(1)-(2)(a)"))
        return rules


class RequirementCompiler:
    def __init__(self, products: List[str]):
        self._products = products

    def compile(self, evidence_items: Iterable[ClauseEvidence]) -> List[Dict[str, Any]]:
        specs: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for evidence in evidence_items:
            template = _SPEC_TEMPLATES.get(evidence.rule_id)
            if not template or evidence.rule_id in seen:
                continue
            seen.add(evidence.rule_id)
            specs.append(
                {
                    **template,
                    "req_id": evidence.rule_id,
                    "applicable_products": self._products,
                    "regulation_clause": evidence.clause_ref,
                    "source_pages": evidence.source_pages,
                    "source_chunk_ids": evidence.source_chunk_ids,
                }
            )
        return specs


class SpecVerifier:
    def filter_valid(self, specs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        valid: List[Dict[str, Any]] = []
        for spec in specs:
            if not spec.get("req_id") or not spec.get("module_zh") or not spec.get("description_zh"):
                continue
            if not spec.get("regulation_clause") and not spec.get("source_pages") and not spec.get("source_chunk_ids"):
                continue
            valid.append(spec)
        return valid


def _format_source_pages(chunk: Dict[str, Any]) -> Optional[str]:
    page_from = chunk.get("page_from")
    page_to = chunk.get("page_to")
    if not page_from:
        return None
    return str(page_from) if not page_to or page_to == page_from else f"{page_from}-{page_to}"


def _format_source_chunk_ids(chunk: Dict[str, Any]) -> List[str]:
    raw_id = chunk.get("id")
    if not raw_id:
        return []
    try:
        return [str(uuid.UUID(str(raw_id)))]
    except (TypeError, ValueError):
        return []


_DRAFT_NOTE_ZH = "规则级规格草案，由原文切片保守生成；后续应结合官方测试程序或协调标准细化测试项。"
_DRAFT_NOTE_EN = "Rule-level draft generated conservatively from source chunks; refine with official test procedures or harmonised standards."

_SPEC_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "NET-RED-001": {
        "module_zh": "网络访问控制",
        "module_en": "Network Access Control",
        "title_zh": "不得危害网络",
        "title_en": "Protect networks",
        "description_zh": "无线电设备必须具备防护能力，确保其功能不会危害网络运行，也不会滥用网络资源导致服务不可接受的降级。",
        "description_en": "Radio equipment must include safeguards so that its functions do not harm networks or misuse network resources causing unacceptable service degradation.",
        "mandatory": "mandatory",
        "priority": "P1",
        "verification_method_zh": "检查产品网络交互、异常流量控制和资源占用保护设计，并通过网络稳定性与滥用场景测试验证。",
        "verification_method_en": "Review network interaction controls and resource-abuse protections, then validate them through network stability and misuse tests.",
        "notes_zh": _DRAFT_NOTE_ZH,
        "notes_en": _DRAFT_NOTE_EN,
    },
    "ENC-RED-001": {
        "module_zh": "数据加密与传输安全",
        "module_en": "Data Encryption and Transmission Security",
        "title_zh": "保护个人数据",
        "title_en": "Protect personal data",
        "description_zh": "无线电设备必须具备保护用户和订户个人数据与隐私的安全措施，避免数据在设备使用过程中被未授权访问、泄露或滥用。",
        "description_en": "Radio equipment must include safeguards to protect users' and subscribers' personal data and privacy against unauthorised access, disclosure, or misuse.",
        "mandatory": "mandatory",
        "priority": "P1",
        "verification_method_zh": "检查数据流、权限控制、传输保护和隐私配置，验证个人数据在采集、传输、存储过程中的保护措施。",
        "verification_method_en": "Inspect data flows, access controls, transmission protection, and privacy settings across collection, transmission, and storage.",
        "notes_zh": _DRAFT_NOTE_ZH,
        "notes_en": _DRAFT_NOTE_EN,
    },
    "AUTH-RED-001": {
        "module_zh": "身份认证与密码管理",
        "module_en": "Authentication and Password Management",
        "title_zh": "防范欺诈滥用",
        "title_en": "Prevent fraud",
        "description_zh": "无线电设备必须支持防欺诈相关安全能力，降低设备被用于欺诈、冒用或未授权交易/通信的风险。",
        "description_en": "Radio equipment must support anti-fraud security capabilities that reduce risks of fraud, impersonation, or unauthorised transactions or communications.",
        "mandatory": "mandatory",
        "priority": "P1",
        "verification_method_zh": "检查身份校验、授权控制、防重放和异常行为检测等设计，并通过欺诈滥用场景测试验证。",
        "verification_method_en": "Review authentication, authorisation, replay protection, and anomaly controls, then validate them with fraud-abuse scenarios.",
        "notes_zh": _DRAFT_NOTE_ZH,
        "notes_en": _DRAFT_NOTE_EN,
    },
    "CMP-FCC-001": {
        "module_zh": "合规认证与测试",
        "module_en": "Compliance Certification and Testing",
        "title_zh": "接受实验室数据",
        "title_en": "Accept CyberLAB data",
        "description_zh": "产品贴标授权应基于经认可 CyberLAB 出具的测试数据；CLA 不得无故重复测试，制造商应保留可追溯的测试证据。",
        "description_en": "Label authorisation should rely on test data from a recognised CyberLAB; the CLA should not require duplicative testing without cause, and manufacturers should keep traceable test evidence.",
        "mandatory": "mandatory",
        "priority": "P1",
        "verification_method_zh": "核验 CyberLAB 认可状态、测试报告编号、测试范围和 CLA 授权记录，确认测试数据可追溯且覆盖申请产品。",
        "verification_method_en": "Verify CyberLAB recognition, report identifiers, test scope, and CLA authorisation records to confirm traceability and product coverage.",
        "notes_zh": _DRAFT_NOTE_ZH,
        "notes_en": _DRAFT_NOTE_EN,
    },
    "CMP-FCC-002": {
        "module_zh": "合规认证与测试",
        "module_en": "Compliance Certification and Testing",
        "title_zh": "上市后监督",
        "title_en": "Post-market surveillance",
        "description_zh": "获得 Cyber Trust Mark 的产品必须接受上市后监督；发现不符合项时，授权方应按要求响应、整改并提交整改证据。",
        "description_en": "Products bearing the Cyber Trust Mark must support post-market surveillance; when non-compliance is found, the authorisation holder must respond, remediate, and provide evidence.",
        "mandatory": "mandatory",
        "priority": "P1",
        "verification_method_zh": "检查上市后抽样测试流程、不符合项通知记录、整改报告和标签授权状态变更记录。",
        "verification_method_en": "Review post-market sampling procedures, non-compliance notices, remediation reports, and label authorisation status changes.",
        "notes_zh": _DRAFT_NOTE_ZH,
        "notes_en": _DRAFT_NOTE_EN,
    },
    "UPD-FCC-001": {
        "module_zh": "安全更新与补丁管理",
        "module_en": "Security Updates and Patch Management",
        "title_zh": "注册表披露",
        "title_en": "Registry disclosures",
        "description_zh": "产品应向公共注册表披露安全更新机制、默认密码修改说明、最低支持期限以及 SBOM/HBOM 等安全透明度信息。",
        "description_en": "The product should disclose security update mechanisms, default password change instructions, minimum support period, and SBOM/HBOM transparency information in the public registry.",
        "mandatory": "mandatory",
        "priority": "P1",
        "verification_method_zh": "核验公共注册表字段、产品安全更新声明、默认凭据配置指南、支持期限声明以及 SBOM/HBOM 披露记录。",
        "verification_method_en": "Verify registry fields, security update statements, default credential guidance, support-period declarations, and SBOM/HBOM disclosures.",
        "notes_zh": _DRAFT_NOTE_ZH,
        "notes_en": _DRAFT_NOTE_EN,
    },
    "CFG-CRA-001": {
        "module_zh": "安全配置与加固",
        "module_en": "Security Configuration and Hardening",
        "title_zh": "无已知漏洞上市",
        "title_en": "No known exploitable vulnerabilities",
        "description_zh": "带数字元素产品投放市场时不得包含已知可利用漏洞，并应提供安全默认配置，包括在适用时支持恢复到原始安全状态。",
        "description_en": "Products with digital elements must be placed on the market without known exploitable vulnerabilities and with secure-by-default configuration, including reset to an original secure state where applicable.",
        "mandatory": "mandatory",
        "priority": "P1",
        "verification_method_zh": "检查发布前漏洞扫描、已知漏洞处置记录、默认配置基线和恢复出厂/原始状态安全性测试。",
        "verification_method_en": "Review pre-release vulnerability scanning, known-vulnerability remediation records, default configuration baselines, and secure reset testing.",
        "notes_zh": _DRAFT_NOTE_ZH,
        "notes_en": _DRAFT_NOTE_EN,
    },
    "UPD-CRA-001": {
        "module_zh": "安全更新与补丁管理",
        "module_en": "Security Updates and Patch Management",
        "title_zh": "安全更新机制",
        "title_en": "Security update mechanism",
        "description_zh": "产品必须支持通过安全更新处置漏洞；在适用时应支持自动安全更新，并在技术可行时将安全更新与功能更新分离。",
        "description_en": "The product must support vulnerability remediation through security updates; where applicable, automatic security updates should be supported and security updates should be separated from feature updates where technically feasible.",
        "mandatory": "mandatory",
        "priority": "P1",
        "verification_method_zh": "验证安全更新通道、更新完整性校验、自动更新配置、用户关闭策略和安全/功能更新分离机制。",
        "verification_method_en": "Validate update channels, update integrity checks, automatic update settings, user opt-out behaviour, and separation of security and functionality updates.",
        "notes_zh": _DRAFT_NOTE_ZH,
        "notes_en": _DRAFT_NOTE_EN,
    },
    "VUL-CRA-001": {
        "module_zh": "漏洞管理与披露",
        "module_en": "Vulnerability Management and Disclosure",
        "title_zh": "SBOM与漏洞文档",
        "title_en": "SBOM and vulnerability records",
        "description_zh": "制造商必须识别并记录产品中的漏洞和组件，并以通用、机器可读格式形成至少覆盖顶层依赖的软件物料清单。",
        "description_en": "Manufacturers must identify and document vulnerabilities and components, including an SBOM in a commonly used machine-readable format covering at least top-level dependencies.",
        "mandatory": "mandatory",
        "priority": "P1",
        "verification_method_zh": "检查组件清单、SBOM 格式、依赖覆盖范围、漏洞登记和版本追踪记录。",
        "verification_method_en": "Review component inventories, SBOM format, dependency coverage, vulnerability registers, and version traceability records.",
        "notes_zh": _DRAFT_NOTE_ZH,
        "notes_en": _DRAFT_NOTE_EN,
    },
    "VUL-CRA-002": {
        "module_zh": "漏洞管理与披露",
        "module_en": "Vulnerability Management and Disclosure",
        "title_zh": "24小时早期预警",
        "title_en": "24-hour early warning",
        "description_zh": "制造商发现产品中存在被主动利用的漏洞后，必须无不当延迟并最迟在24小时内通过单一报告平台向指定 CSIRT 和 ENISA 提交早期预警通知。",
        "description_en": "After becoming aware of an actively exploited vulnerability, the manufacturer must submit an early warning notification without undue delay and within 24 hours via the single reporting platform to the designated CSIRT and ENISA.",
        "mandatory": "mandatory",
        "priority": "P1",
        "verification_method_zh": "检查漏洞监测、事件分级、24小时通知 SLA、报告平台流程和通知记录。",
        "verification_method_en": "Review vulnerability monitoring, incident triage, 24-hour notification SLA, reporting-platform workflow, and notification records.",
        "notes_zh": _DRAFT_NOTE_ZH,
        "notes_en": _DRAFT_NOTE_EN,
    },
}
