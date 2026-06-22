"""
collector/document/spec_prompt.py
规格要求提取 Prompt - 只负责构建 Prompt，无其他依赖
"""
from __future__ import annotations
from datetime import date

FUNCTIONAL_MODULES = [
    "身份认证与密码管理",
    "网络访问控制",
    "数据加密与传输安全",
    "安全更新与补丁管理",
    "日志与审计",
    "漏洞管理与披露",
    "物理与接口安全",
    "安全配置与加固",
    "供应链安全",
    "合规认证与测试",
]

PRODUCT_NAMES_ZH = {
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

PRODUCT_NAMES_EN = {
    "enterprise_router": "Enterprise Router",
    "home_router": "Home Router",
    "switch": "Network Switch",
    "firewall_utm": "Firewall/UTM",
    "wireless_ap": "Wireless AP",
    "industrial_gateway": "Industrial Gateway",
    "sd_wan": "SD-WAN",
    "security_gateway": "Security Gateway",
    "cloud_desktop": "Cloud Desktop",
    "software": "Software",
}

ALL_PRODUCTS = list(PRODUCT_NAMES_ZH.keys())


def build_spec_extraction_prompt(
    document_text: str,
    regulation_name: str,
    country_code: str,
    applicable_products: list,
    max_chars: int = 60000,
    window_label: str | None = None,
    full_document_hint: str | None = None,
) -> str:
    """
    构建规格提取 Prompt。
    将法规原文转化为产品工程规格要求，按功能模块组织，中英双语输出。
    """
    if len(document_text) > max_chars:
        half = max_chars // 2
        text = document_text[:half] + "\n\n[...中间内容省略...]\n\n" + document_text[-half:]
    else:
        text = document_text

    products_str = "、".join(
        f"{PRODUCT_NAMES_ZH.get(p, p)}({PRODUCT_NAMES_EN.get(p, p)})"
        for p in applicable_products
    )
    modules_str = "\n".join(f"- {m}" for m in FUNCTIONAL_MODULES)
    today = date.today().isoformat()

    return f"""你是一名资深网络设备产品合规工程师，擅长将网络安全法规转化为产品可执行的工程规格要求。
你的角色是“规格提取器”，不是“真伪判定器”或“联网检索器”。
只能基于下方提供的本地法规原文提取规格，不得补充外部知识，不得判断法规真实性。

## 任务
请阅读以下法规原文，提取并转化为产品规格要求（Product Security Requirements）。

## 基本信息
- 法规名称：{regulation_name}
- 适用国家/地区：{country_code}
- 适用产品：{products_str}
- 生成日期：{today}
{f"- 当前处理窗口：{window_label}" if window_label else ""}
{f"- 全文处理提示：{full_document_hint}" if full_document_hint else ""}

## 功能模块分类
请将所有规格要求按以下功能模块分类：
{modules_str}

## 输出格式要求
输出一个 JSON 数组，每个元素是一条规格要求：

[
  {{
    "req_id": "模块缩写-序号，如 AUTH-001、NET-002、ENC-003",
    "module_zh": "功能模块中文名，从上方列表选择",
    "module_en": "功能模块英文名",
    "title_zh": "规格要求标题（中文，15字以内）",
    "title_en": "Requirement title (English, within 10 words)",
    "description_zh": "详细规格描述（中文），必须是可测试、可验证的工程语言，如：设备必须在首次登录时强制用户修改默认密码，密码长度不得少于8位，必须包含大小写字母和数字",
    "description_en": "Detailed specification (English), must be testable and verifiable engineering language",
    "applicable_products": ["适用的产品代码列表，从：enterprise_router/home_router/switch/firewall_utm/wireless_ap/industrial_gateway/sd_wan/security_gateway/cloud_desktop/software 中选择"],
    "mandatory": "mandatory（法规强制）或 recommended（最佳实践）",
    "regulation_clause": "对应法规条款编号，如 Article 3(3)(d)，无则填null",
    "source_pages": "可选，引用页码范围，如 12-13；无法确定则填null",
    "verification_method_zh": "验证方法（中文）：如何测试该要求是否满足",
    "verification_method_en": "Verification method (English)",
    "priority": "P1（必须满足才能销售）/ P2（重要但有过渡期）/ P3（推荐最佳实践）",
    "notes_zh": "补充说明、豁免条件、实施建议（中文）",
    "notes_en": "Additional notes (English)"
  }}
]

## 转化原则
1. 法规条款 → 工程规格：将抽象法规语言转化为具体可执行的技术要求
2. 可测试性：每条规格必须能够通过测试验证，描述中包含可量化指标
3. 产品差异化：不同产品类型的要求可能不同，请在 applicable_products 中准确标注
4. 完整覆盖：确保法规所有强制要求都被覆盖，不遗漏
5. 模块分类准确：每条规格只属于一个功能模块
6. 优先给出明确的 regulation_clause；若只能定位到页码，请填写 source_pages
7. 如果这是全文中的一个窗口，只提取当前窗口明确出现的要求，不要臆造其他窗口内容
8. req_id 编号规则：
   - AUTH: 身份认证与密码管理
   - NET: 网络访问控制
   - ENC: 数据加密与传输安全
   - UPD: 安全更新与补丁管理
   - LOG: 日志与审计
   - VUL: 漏洞管理与披露
   - PHY: 物理与接口安全
   - CFG: 安全配置与加固
   - SUP: 供应链安全
   - CMP: 合规认证与测试

## 法规原文
{text}

只输出JSON数组，不输出任何其他文字。"""


def build_spec_merge_prompt(
    regulation_name: str,
    country_code: str,
    applicable_products: list,
    candidate_specs: list,
) -> str:
    products_str = "、".join(
        f"{PRODUCT_NAMES_ZH.get(p, p)}({PRODUCT_NAMES_EN.get(p, p)})"
        for p in applicable_products
    )
    modules_str = "\n".join(f"- {m}" for m in FUNCTIONAL_MODULES)
    candidates_json = json_dumps(candidate_specs)
    today = date.today().isoformat()

    return f"""你是一名资深网络设备产品合规工程师，正在对“全文分段提取”得到的候选规格做最终归并。
你的职责是：去重、合并、补齐字段、统一 req_id 编号，输出最终规格数组。
禁止联网，禁止补充候选数组之外的法规要求，禁止凭常识新增条目。

## 基本信息
- 法规名称：{regulation_name}
- 适用国家/地区：{country_code}
- 适用产品：{products_str}
- 生成日期：{today}

## 功能模块分类
{modules_str}

## 归并规则
1. 删除重复要求：同一 regulation_clause、同一标题或同一工程要求视为同一条
2. 合并互补字段：不同窗口抽到的相同要求，如果一个条目有条款号、另一个有验证方法，需要合并成一条
3. 保持保守：不能凭经验补出候选数组里没有出现的要求
4. req_id 必须在最终结果里唯一
5. 每条至少保留 regulation_clause 或 source_pages 之一
6. 只保留可执行、可验证的工程规格语言

## 候选规格数组
{candidates_json}

只输出最终 JSON 数组，不输出任何其他文字。"""


def json_dumps(value) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)
