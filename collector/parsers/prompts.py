"""
collector/parsers/prompts.py - v2.0
优化：分层扫描 + 时效性 + 字段质量 + 噪音过滤
"""
from __future__ import annotations
from typing import List
from datetime import date

SYSTEM_PROMPT = """你是一名专业的全球网络安全合规专家，专注于网络设备（路由器、交换机、防火墙、无线AP、工业网关等）的出口合规。

## 最重要：数据时效性
- 今天日期：{today}
- 所有日期字段必须基于今天的联网搜索结果，禁止使用训练数据中的历史日期
- 生效日期是最关键字段，必须搜索官方来源确认，不得猜测
- 若法规有多个阶段生效日期，全部列出在 remarks 中，effective_date 填最近强制日期

## 输出规则
1. 只输出 JSON，禁止输出解释文字或 markdown 代码块标记
2. 不确定的字段填 null，禁止填猜测内容
3. 日期格式：YYYY-MM-DD
4. 文字描述用中文，法规/认证名称保留英文原名
5. applicable_products 只从此列表选择：
   enterprise_router, home_router, switch, firewall_utm,
   wireless_ap, industrial_gateway, sd_wan, security_gateway,
   cloud_desktop, software
6. entry_type 只能是：regulation / standard / certification
7. mandatory 只能是：mandatory / voluntary / recommended
8. status 只能是：active / deprecated / draft

## 噪音过滤（绝对不纳入）
- 电气安全：CCC、UL、PSE、CE-LVD、CB
- 电磁兼容：EMC、FCC Part 15射频、TELEC、KCC射频
- 环保：RoHS、WEEE、能效标签、ErP
- 质量管理：ISO 9001、ISO 14001
- 无线电频率许可：SRRC、ISED射频
- 纯信息安全管理体系：ISO 27001（除非强制认证要求）

## 字段质量要求
- name：必须是官方完整英文名称，不能缩写
- issuing_body：必须是机构官方名称
- official_url：必须是政府官网或标准机构官网直链，不能是新闻/博客
- confidence_score：搜到官方原文填90-100，权威二手来源填70-89，不确定填50-69
"""

def get_system_prompt() -> str:
    return SYSTEM_PROMPT.format(today=date.today().isoformat())

_FIELDS = '''  {
    "name": "法规/认证完整英文官方名称",
    "name_local": "本地语言官方名称（无则null）",
    "entry_type": "regulation|standard|certification",
    "mandatory": "mandatory|voluntary|recommended",
    "status": "active|deprecated|draft",
    "country_code": "COUNTRY_CODE",
    "issuing_body": "发布机构/认证机构官方全称",
    "technical_standards": ["引用的技术标准列表"],
    "regulation_basis": ["所依据的上位法规（认证类必填）"],
    "effective_date": "强制生效日期YYYY-MM-DD，必须搜索确认，不确定填null",
    "transition_end_date": "过渡期截止YYYY-MM-DD，无则null",
    "validity_period": "证书有效期如3年，法规类填null",
    "published_date": "官方发布日期YYYY-MM-DD",
    "applicable_products": ["从产品列表中选择"],
    "scope_description": "适用范围和条件，100字以内",
    "requirements": {
      "key_requirements": ["最核心3-5条技术要求"],
      "assessment_route": "合规证明路径",
      "penalty": "违规处罚说明",
      "special_notes": "分阶段时间表、豁免条件"
    },
    "testing_bodies": ["官方认可的测试机构"],
    "assessment_procedure": "获得合规证明的步骤",
    "official_url": "政府/标准机构官网原始链接",
    "remarks": "与其他法规关联、对出口商的关键影响",
    "confidence_score": 85
  }'''

def _fields(cc): return _FIELDS.replace("COUNTRY_CODE", cc)

def build_regulation_scan_prompt(country_code, country_name, existing_names):
    existing_str = "\n".join(f"  - {n}" for n in existing_names) if existing_names else "  （暂无）"
    today = date.today().isoformat()
    year = date.today().year
    return f"""请联网搜索，列出{country_name}（{country_code}）针对网络设备的【强制性网络安全法规】。

今天：{today}

搜索关键词（依次搜索）：
1. "{country_name} cybersecurity law network device mandatory {year}"
2. "{country_name} network security regulation router firewall enforcement {year}"
3. "{country_name} IoT security regulation mandatory compliance {year}"

已有记录（勿重复，但请核实生效日期）：
{existing_str}

重点关注：近2年新发布/修订的法规、有明确生效日期的法规、含过渡期安排的法规。

生成 JSON 数组，entry_type 统一填 "regulation"：
[
{_fields(country_code)}
]

只输出JSON数组。"""

def build_certification_scan_prompt(country_code, country_name, existing_names):
    existing_str = "\n".join(f"  - {n}" for n in existing_names) if existing_names else "  （暂无）"
    today = date.today().isoformat()
    year = date.today().year
    return f"""请联网搜索，列出{country_name}（{country_code}）针对网络设备的【网络安全认证方案】。

今天：{today}

搜索关键词：
1. "{country_name} cybersecurity certification scheme network equipment {year}"
2. "{country_name} network device security certification label mark"
3. "{country_name} IoT cybersecurity certification authority {year}"

已有记录（勿重复）：
{existing_str}

重点关注：强制认证、主流自愿认证、认证机构和申请流程、证书有效期。

生成 JSON 数组，entry_type 统一填 "certification"：
[
{_fields(country_code)}
]

只输出JSON数组。"""

def build_standard_scan_prompt(country_code, country_name, existing_names):
    existing_str = "\n".join(f"  - {n}" for n in existing_names) if existing_names else "  （暂无）"
    today = date.today().isoformat()
    return f"""请联网搜索，列出{country_name}（{country_code}）网络设备须满足的【强制引用技术标准】。

今天：{today}

搜索关键词：
1. "{country_name} cybersecurity technical standard network device mandatory reference"
2. "{country_name} router firewall security standard IEC ETSI NIST mandatory"

已有记录（勿重复）：
{existing_str}

重点关注：被法规强制引用的标准（非自愿）、含具体测试方法的标准、最新版本号。

生成 JSON 数组，entry_type 统一填 "standard"：
[
{_fields(country_code)}
]

只输出JSON数组。"""

def build_country_scan_prompt(country_code, country_name, product_types, existing_names):
    """兼容旧调用接口"""
    existing_str = "\n".join(f"  - {n}" for n in existing_names) if existing_names else "  （暂无）"
    today = date.today().isoformat()
    year = date.today().year
    return f"""请联网搜索，全面列出{country_name}（{country_code}）对网络设备的【当前有效】网络安全法规、认证和标准。

今天：{today}

分三轮搜索：
1. 强制法规："{country_name} cybersecurity regulation network device mandatory {year}"
2. 认证体系："{country_name} cybersecurity certification scheme network equipment 2025"
3. 技术标准："{country_name} cybersecurity technical standard router firewall IEC ETSI"

已有记录（勿重复，但请核实生效日期是否有变化）：
{existing_str}

要求：三轮结果合并输出，预期至少10-15条；effective_date 是最关键字段必须搜索确认。

生成 JSON 数组：
[
{_fields(country_code)}
]

只输出JSON数组。"""

def build_incremental_check_prompt(record: dict) -> str:
    today = date.today().isoformat()
    year = date.today().year
    return f"""请今天联网搜索以下法规/认证的【最新状态】，重点核实日期变化。

今天：{today}
名称：{record.get('name')}
国家：{record.get('country_code')}
当前生效日期：{record.get('effective_date')}
当前过渡期截止：{record.get('transition_end_date')}
当前状态：{record.get('status')}
官方链接：{record.get('official_url')}

重点搜索：
1. 生效日期是否推迟/提前？搜索"{record.get('name')} effective date {year}"
2. 过渡期是否延长？
3. 是否有新修正案？
4. 是否已废止？

输出 JSON：
{{
  "has_changes": true或false,
  "change_summary": "一句话描述最重要变更，无变更填null",
  "updated_fields": {{"字段名": "新值（只填确认有变化的字段）"}},
  "confidence_score": 85,
  "search_date": "{today}",
  "sources": ["原始来源URL"]
}}

只输出JSON。"""

def build_document_parse_prompt(document_text: str, country_code: str, document_name: str, max_chars: int = 60000) -> str:
    """从法规原文PDF提取结构化数据"""
    if len(document_text) > max_chars:
        half = max_chars // 2
        text = document_text[:half] + "\n\n[...中间内容省略...]\n\n" + document_text[-half:]
    else:
        text = document_text
    today = date.today().isoformat()
    return f"""请从以下法规原文中提取结构化的网络安全合规信息。所有内容必须来自原文，不得添加外部信息。
你在这里的角色是“原文解析器”，不是“真实性判定器”。
禁止判断该法规是否真实、是否官方、是否应该标记为 verified/suspicious/quarantined。

文档：{document_name}
国家：{country_code}
今天：{today}

提取要点：
1. 适用范围（哪些产品必须遵守，有哪些豁免）
2. 生效日期和过渡期安排
3. 核心技术要求（含原文条款编号）
4. 合规证明路径（自我声明/第三方认证）
5. 引用的技术标准
6. 违规处罚条款
7. 主管执行机构

输出 JSON：
{{
  "name": "法规官方名称",
  "name_local": "本地语言名称",
  "entry_type": "regulation",
  "mandatory": "mandatory",
  "status": "active",
  "country_code": "{country_code}",
  "issuing_body": "主管机构官方名称",
  "technical_standards": ["原文引用的技术标准"],
  "effective_date": "强制生效日期YYYY-MM-DD",
  "transition_end_date": "过渡期截止YYYY-MM-DD或null",
  "published_date": "发布日期YYYY-MM-DD",
  "applicable_products": ["enterprise_router/home_router/switch/firewall_utm/wireless_ap/industrial_gateway/sd_wan/security_gateway/cloud_desktop/software"],
  "scope_description": "适用范围原文摘要",
  "requirements": {{
    "key_requirements": ["核心技术要求，含原文条款编号"],
    "assessment_route": "合规证明路径",
    "penalty": "违规处罚摘要",
    "special_notes": "过渡期安排、豁免条件"
  }},
  "testing_bodies": ["测试/认证机构"],
  "assessment_procedure": "合规评估流程",
  "official_url": null,
  "remarks": "其他重要信息",
  "confidence_score": 98,
  "data_source": "document_parse"
}}

原文：
{text}

只输出JSON。"""


def build_official_source_fallback_prompt(source: dict, fetch_error: str | None = None) -> str:
    allowed_domains = source.get("allowed_domains") or []
    allowed_domains_text = "\n".join(f"- {domain}" for domain in allowed_domains) or "- （未配置）"
    entry_types = ", ".join(source.get("entry_type_scope") or ["regulation"])
    parser_config = source.get("parser_config") or {}
    url_patterns = parser_config.get("url_patterns") or []
    url_patterns_text = "\n".join(f"- {pattern}" for pattern in url_patterns) or "- （未配置）"
    error_text = fetch_error or "未提供错误详情"
    today = date.today().isoformat()

    return f"""请联网搜索并恢复以下【官方源】的可访问官方页面或官方 PDF。
你在这里的角色是“官方链接发现助手”，不是“真实性审核员”。
你只能返回候选官方页面/PDF，不得替系统决定 verified/suspicious/quarantined。

今天：{today}
国家/地区：{source.get("country_name") or source.get("country_code")}
官方机构：{source.get("name")}
基础站点：{source.get("base_url")}
原列表页：{source.get("list_url")}
允许域名（必须严格命中其一，否则丢弃）：
{allowed_domains_text}

本次官方抓取失败原因：
{error_text}

目标范围：
- 只寻找与该官方机构直接相关的 {entry_types} 内容
- 优先寻找官方 PDF 原文
- 若无 PDF，可返回官方详情页
- 允许返回列表页中的替代栏目页，但必须属于上述官方域名

提示性匹配线索：
{url_patterns_text}

绝对禁止：
- 新闻站、博客、行业媒体、社交媒体、第三方数据库、镜像站
- 不在允许域名内的 URL
- 猜测标题或捏造发布日期

输出规则：
1. 只输出 JSON 数组
2. 找不到可信官方结果时，输出 []
3. 每个对象仅允许包含这些字段：
   - title
   - detail_url
   - artifact_url
   - published_date
   - summary
   - issuing_body
   - entry_type
   - why_official
4. detail_url 和 artifact_url 至少提供一个
5. published_date 不确定时填 null
6. why_official 必须简要说明为什么这是官方来源

输出示例：
[
  {{
    "title": "Cybersecurity Labelling Scheme for IoT",
    "detail_url": "https://www.csa.gov.sg/our-programmes/...",
    "artifact_url": "https://www.csa.gov.sg/docs/default-source/.../cls-iot.pdf",
    "published_date": "2025-01-10",
    "summary": "新加坡官方 IoT 网络安全标签计划",
    "issuing_body": "Cyber Security Agency of Singapore",
    "entry_type": "certification",
    "why_official": "URL 位于 csa.gov.sg 官方域名下，内容为官方计划页面"
  }}
]

只输出 JSON 数组。"""
