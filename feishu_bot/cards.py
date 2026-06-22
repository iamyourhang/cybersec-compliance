"""
feishu_bot/cards.py
飞书卡片模板
"""
from __future__ import annotations
from datetime import date
from typing import Any, Dict, List, Optional


def build_query_result_card(query, product_name, country_name, country_code, items, total):
    mandatory = [i for i in items if i.get("mandatory") == "mandatory"]
    voluntary = [i for i in items if i.get("mandatory") != "mandatory"]

    elements = [
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**产品类型**\n{product_name}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**目标国家**\n{country_name} ({country_code})"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**强制认证**\n{len(mandatory)} 项"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**自愿认证**\n{len(voluntary)} 项"}},
            ]
        },
        {"tag": "hr"},
    ]

    if mandatory:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**🔴 强制合规要求**"}})
        for item in mandatory[:8]:
            eff = item.get("effective_date", "")
            eff_str = f" · 生效: {eff}" if eff else ""
            icon = {"regulation": "📋", "certification": "🏆", "standard": "📐"}.get(item.get("entry_type", ""), "•")
            name = item.get("name", "")[:50]
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"{icon} **{name}**{eff_str}"}})

    if mandatory and voluntary:
        elements.append({"tag": "hr"})

    if voluntary:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**🟡 自愿/推荐认证**"}})
        for item in voluntary[:3]:
            name = item.get("name", "")[:50]
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"• {name}"}})

    if total > 11:
        elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"仅显示前{min(total,11)}条，完整清单请访问管理后台"}]})

    elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"网安合规助手 · 查询: {query[:30]}"}]})

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": f"🔍 {country_name}市场合规要求"}, "template": "blue"},
        "elements": elements,
    }


def build_help_card():
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": "📖 网安合规助手 · 使用指南"}, "template": "turquoise"},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": "**💬 自然语言查询**\n直接 @我 用中文提问，例如："}},
            {"tag": "div", "text": {"tag": "lark_md", "content": "• 交换机卖美国需要什么认证？\n• 路由器出口欧盟有哪些强制法规？\n• CRA什么时候生效？\n• 防火墙出口日本需要哪些认证？"}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "**⌨️ 快捷指令**"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": "• `/query <产品> <国家>` — 精确查询\n• `/upcoming` — 查看近30天即将生效法规\n• `/help` — 显示此帮助"}},
            {"tag": "hr"},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "网安合规助手 · 数据每周自动更新"}]},
        ]
    }


def build_upcoming_card(items):
    elements = []
    for item in items[:10]:
        days = item.get("days_until_effective", 0)
        color = "🔴" if days <= 7 else "🟡" if days <= 30 else "🟢"
        days_str = "今日生效" if days == 0 else f"{days}天后生效"
        name = item.get("name", "")[:45]
        cc = item.get("country_code", "")
        cn = item.get("country_name", "")
        eff = item.get("effective_date", "")
        milestone = item.get("milestone_label_zh") or "生效/适用节点"
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"{color} **{name}**\n{cn} ({cc}) · {milestone} · {days_str} · {eff}"}})
        elements.append({"tag": "hr"})

    if not items:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "🎉 近30天内暂无法规生效"}})

    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"网安合规助手 · {date.today().isoformat()}"}]})

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": "⏰ 近30天即将生效法规"}, "template": "orange"},
        "elements": elements,
    }


def build_error_card(msg):
    return {
        "config": {"wide_screen_mode": False},
        "header": {"title": {"tag": "plain_text", "content": "❓ 未能理解您的问题"}, "template": "red"},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": msg}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "发送 `/help` 查看使用指南"}},
        ]
    }


def build_regulation_detail_card(keyword, items):
    elements = []
    for item in items:
        eff = item.get("effective_date", "")
        eff_str = f" · 生效: **{eff}**" if eff else ""
        icon = {"regulation": "📋", "certification": "🏆", "standard": "📐"}.get(item.get("entry_type", ""), "•")
        mand = {"mandatory": "🔴 强制", "voluntary": "🟡 自愿", "recommended": "🟢 推荐"}.get(item.get("mandatory", ""), "")
        name = item.get("name", "")
        cn = item.get("country_name", "")
        cc = item.get("country_code", "")
        desc = (item.get("scope_description") or "")[:120]
        content_str = f"{icon} **{name}**\n{cn} ({cc}) · {mand}{eff_str}\n{desc}"
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content_str}})
        if item.get("official_url"):
            url = item["official_url"]
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"🔗 [官方链接]({url})"}})
        elements.append({"tag": "hr"})

    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"网安合规助手 · 查询: {keyword}"}]})

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": f"🔍 {keyword} 相关法规"}, "template": "purple"},
        "elements": elements,
    }


def build_rag_answer_card(question: str, result: Dict[str, Any]):
    citations = result.get("citations", [])
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**结论**\n{result.get('answer', '—')}"}} ,
    ]
    if citations:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**依据片段**"}})
        for citation in citations[:3]:
            clause = citation.get("clause_ref") or "未识别条款"
            page = f"第 {citation['page_from']}" if citation["page_from"] == citation["page_to"] else f"第 {citation['page_from']}-{citation['page_to']}"
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"• **{citation['document_name']}** · {clause} · {page} 页\n"
                            f"{citation['excerpt']}"
                        ),
                    },
                }
            )
    if result.get("related_records"):
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**来源**\n" + "\n".join(
                        f"• {item['name']} ({item['country_code']})"
                        for item in result["related_records"][:3]
                    ),
                },
            }
        )
    elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"网安合规助手 · 问题: {question[:40]}"}]})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": "📚 法规原文问答"}, "template": "blue"},
        "elements": elements,
    }
