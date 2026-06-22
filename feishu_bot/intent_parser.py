"""
feishu_bot/intent_parser.py
意图解析 - 直接用AI，不维护规则表
"""
from __future__ import annotations
import json
import logging
import re
from collector.providers.channel_router import get_channel_router
from collector.parsers.compliance_parser import extract_json_from_text

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是网安合规助手的意图解析器，专注于网络设备出口合规领域。

分析用户问题，输出JSON：
{
  "intent": "query_compliance|query_regulation|rag_query|upcoming|help|unknown",
  "product_code": "从以下选一个或null：enterprise_router/home_router/switch/firewall_utm/wireless_ap/industrial_gateway/sd_wan/security_gateway/cloud_desktop/software",
  "country_code": "ISO 2位国家代码或null，地区映射：东南亚→SG，中东/海湾/GCC→AE，沙特→SA，非洲→NG，欧洲/欧盟→EU，拉美/南美→BR，南亚→IN",
  "regulation_name": "法规名称关键词或null",
  "mandatory_only": false,
  "question": "原始问题或重写后的简洁问题"
}

规则：
- query_compliance：询问某产品在某国需要什么认证/法规/合规要求
- query_regulation：询问某个具体法规的内容/生效时间/详情
- rag_query：询问法规条款、原文要求、处罚、适用范围、默认安全要求等需要引用原文证据的问题
- upcoming：询问近期即将生效的法规
- help：帮助/使用说明
- unknown：无法识别或闲聊

只输出JSON，不输出其他文字。"""

# 只保留最简单的指令识别（避免API调用）
QUICK_COMMANDS = {
    "/help": "help", "帮助": "help", "使用说明": "help",
    "/upcoming": "upcoming", "即将生效": "upcoming", "近期生效": "upcoming",
}


def parse_intent(text: str) -> dict:
    """解析用户意图，简单指令直接返回，其余全走AI"""
    # 清理@提及
    text = re.sub(r'@\S+\s*', '', text).strip()
    if not text:
        return {"intent": "unknown"}

    # 快速指令匹配
    for cmd, intent in QUICK_COMMANDS.items():
        if cmd in text.lower():
            return {"intent": intent}

    # 全部走AI解析
    return _parse_with_ai(text)


def _parse_with_ai(text: str) -> dict:
    """调用AI解析意图"""
    try:
        router = get_channel_router()
        resp = router.chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=150,
            enable_web_search=False,
        )
        json_str = extract_json_from_text(resp.content)
        result = json.loads(json_str)
        logger.info("AI意图解析: %s -> %s", text[:40], result)
        return result
    except Exception as e:
        logger.warning("AI意图解析失败: %s", e)
        return {"intent": "unknown"}
