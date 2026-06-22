"""
feishu_bot/client.py
飞书 API 客户端 - 只负责与飞书 API 通信
"""
from __future__ import annotations
import logging
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from config.settings import get_settings

logger = logging.getLogger(__name__)

def get_client() -> lark.Client:
    s = get_settings()
    return lark.Client.builder()\
        .app_id(s.feishu.app_id)\
        .app_secret(s.feishu.app_secret)\
        .log_level(lark.LogLevel.WARNING)\
        .build()

def send_message(receive_id: str, content: str, receive_id_type: str = "chat_id") -> bool:
    """发送文本消息"""
    import json
    client = get_client()
    req = CreateMessageRequest.builder()\
        .receive_id_type(receive_id_type)\
        .request_body(CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type("text")
            .content(json.dumps({"text": content}, ensure_ascii=False))
            .build())\
        .build()
    resp = client.im.v1.message.create(req)
    if not resp.success():
        logger.error("发送文本消息失败: %s %s", resp.code, resp.msg)
        return False
    return True

def send_card(receive_id: str, card: dict, receive_id_type: str = "chat_id") -> bool:
    """发送卡片消息"""
    import json
    client = get_client()
    req = CreateMessageRequest.builder()\
        .receive_id_type(receive_id_type)\
        .request_body(CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type("interactive")
            .content(json.dumps(card, ensure_ascii=False))
            .build())\
        .build()
    resp = client.im.v1.message.create(req)
    if not resp.success():
        logger.error("发送卡片消息失败: %s %s", resp.code, resp.msg)
        return False
    return True

def reply_message(message_id: str, content: str, msg_type: str = "text") -> bool:
    """回复消息"""
    import json
    client = get_client()
    if msg_type == "text":
        body_content = json.dumps({"text": content}, ensure_ascii=False)
    else:
        body_content = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content

    req = ReplyMessageRequest.builder()\
        .message_id(message_id)\
        .request_body(ReplyMessageRequestBody.builder()
            .content(body_content)
            .msg_type(msg_type)
            .build())\
        .build()
    resp = client.im.v1.message.reply(req)
    if not resp.success():
        logger.error("回复消息失败: %s %s", resp.code, resp.msg)
        return False
    return True

def reply_card(message_id: str, card: dict) -> bool:
    """回复卡片消息"""
    import json
    client = get_client()
    req = ReplyMessageRequest.builder()\
        .message_id(message_id)\
        .request_body(ReplyMessageRequestBody.builder()
            .content(json.dumps(card, ensure_ascii=False))
            .msg_type("interactive")
            .build())\
        .build()
    resp = client.im.v1.message.reply(req)
    if not resp.success():
        logger.error("回复卡片失败: %s %s", resp.code, resp.msg)
        return False
    return True
