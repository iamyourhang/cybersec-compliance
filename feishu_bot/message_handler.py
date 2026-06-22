"""
feishu_bot/message_handler.py
消息处理器 - 支持单问题和多问题批量回复
"""
from __future__ import annotations
import logging
import re
import time

from feishu_bot.intent_parser import parse_intent
from feishu_bot.query_handler import query_compliance, query_rag, query_regulation, query_upcoming
from feishu_bot.cards import (
    build_query_result_card, build_help_card,
    build_upcoming_card, build_error_card,
    build_rag_answer_card, build_regulation_detail_card,
)
from feishu_bot.client import reply_card, reply_message

logger = logging.getLogger(__name__)

GREETINGS = ["你好", "hello", "hi", "您好", "早上好", "下午好", "晚上好", "在吗", "在", "哈喽", "嗨", "hey"]


def handle_message(message_id: str, text: str, sender_id: str) -> None:
    """处理收到的消息，支持多问题批量回复"""
    text = re.sub(r'@\S+\s*', '', text).strip()
    if not text:
        return

    questions = [l.strip() for l in re.split(r'[\n•·]', text) if l.strip() and len(l.strip()) > 1]
    if not questions:
        return

    logger.info("收到 %d 个问题 [%s]", len(questions), sender_id[:8])

    if len(questions) == 1:
        _handle_single(message_id, questions[0])
        return

    reply_message(message_id, f"收到 {len(questions)} 个问题，逐一为您查询 🔍")
    time.sleep(0.5)
    for i, q in enumerate(questions, 1):
        try:
            logger.info("处理第 %d/%d 条: %s", i, len(questions), q[:60])
            _handle_single(message_id, q)
            time.sleep(0.5)
        except Exception as e:
            logger.error("第 %d 条处理失败: %s", i, e)


def _handle_single(message_id: str, text: str) -> None:
    """处理单条问题"""
    logger.info("处理问题: %s", text[:80])
    try:
        # 打招呼直接返回帮助卡片
        if any(g in text.lower() for g in GREETINGS):
            reply_card(message_id, build_help_card())
            return

        intent = parse_intent(text)
        intent_type = intent.get("intent", "unknown")
        logger.info("意图: %s", intent_type)

        if intent_type == "help":
            reply_card(message_id, build_help_card())

        elif intent_type == "upcoming":
            items = query_upcoming(30)
            reply_card(message_id, build_upcoming_card(items))

        elif intent_type == "query_compliance":
            product_code = intent.get("product_code")
            country_code = intent.get("country_code")
            if not product_code or not country_code:
                if not product_code and country_code:
                    from feishu_bot.query_handler import query_all_by_country
                    result = query_all_by_country(country_code)
                    reply_card(message_id, build_query_result_card(
                        query=text,
                        product_name="所有产品",
                        country_name=result["country_name"],
                        country_code=country_code,
                        items=result["items"],
                        total=result["total"],
                    ))
                elif product_code and not country_code:
                    reply_card(message_id, build_error_card(
                        f"已识别产品：**{product_code}**\n\n请告诉我目标销售国家？\n例如：交换机卖到 **美国/欧盟/日本**"
                    ))
                else:
                    reply_card(message_id, build_error_card(
                        "请告诉我：\n• **什么产品**（交换机、路由器、防火墙...）\n• **卖到哪个国家**（美国、欧盟、日本...）\n\n例如：**交换机** 卖 **美国** 需要什么认证？"
                    ))
                return
                return

            result = query_compliance(
                product_code=product_code,
                country_code=country_code,
                mandatory_only=intent.get("mandatory_only", False),
            )

            if result["total"] == 0:
                reply_card(message_id, build_error_card(
                    f"暂无 **{result['product_name']}** 出口到 **{result['country_name']}** 的合规数据。\n\n"
                    "可能原因：该国数据尚未收录，或该产品在该国无特定要求。"
                ))
                return

            reply_card(message_id, build_query_result_card(
                query=text,
                product_name=result["product_name"],
                country_name=result["country_name"],
                country_code=country_code,
                items=result["items"],
                total=result["total"],
            ))

        elif intent_type == "query_regulation":
            keyword = intent.get("regulation_name", "")
            country_code = intent.get("country_code")
            if not keyword:
                reply_card(message_id, build_error_card(
                    "请告诉我您想查询哪个法规？\n例如：**CRA** 是什么？**PSTI** 什么时候生效？"
                ))
                return

            items = query_regulation(keyword, country_code)
            if not items:
                reply_card(message_id, build_error_card(
                    f"未找到包含「{keyword}」的法规。\n请尝试用完整名称或缩写查询。"
                ))
                return

            reply_card(message_id, build_regulation_detail_card(keyword, items))

        elif intent_type == "rag_query":
            result = query_rag(
                question=intent.get("question") or text,
                country_code=intent.get("country_code"),
                product_code=intent.get("product_code"),
            )
            reply_card(message_id, build_rag_answer_card(text, result))

        else:
            result = query_rag(question=text)
            if result.get("status") == "answered":
                reply_card(message_id, build_rag_answer_card(text, result))
            else:
                reply_card(message_id, build_error_card(
                    "没有理解您的问题 😅\n\n"
                    "试试这样问：\n"
                    "• **交换机** 卖 **美国** 需要什么认证？\n"
                    "• **防火墙** 出口 **欧盟** 有哪些强制要求？\n"
                    "• **CRA** 什么时候生效？\n\n"
                    "发送 `/help` 查看完整使用指南"
                ))

    except Exception as e:
        logger.error("处理消息失败: %s", e, exc_info=True)
        try:
            reply_message(message_id, f"⚠️ 查询时发生错误，请稍后重试")
        except Exception:
            pass
