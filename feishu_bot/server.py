"""
feishu_bot/server.py
飞书事件接收服务
"""
from __future__ import annotations
import json
import logging
import threading
from fastapi import FastAPI, Request
from feishu_bot.message_handler import handle_message
from utils.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
app = FastAPI(title="飞书机器人", docs_url=None, redoc_url=None)

_processed = set()
_lock = threading.Lock()


@app.post("/feishu/webhook")
async def feishu_webhook(request: Request):
    body = await request.body()
    try:
        data = json.loads(body)
    except Exception:
        return {"code": 0}

    # URL验证
    if "challenge" in data:
        return {"challenge": data["challenge"]}

    # 打印完整事件类型便于调试
    event_type = data.get("header", {}).get("event_type", "")
    logger.info("收到事件: %s", event_type)

    if event_type != "im.message.receive_v1":
        return {"code": 0}

    event = data.get("event", {})
    message = event.get("message", {})
    message_id = message.get("message_id", "")
    msg_type = message.get("message_type", "")

    logger.info("消息类型=%s message_id=%s", msg_type, message_id)

    # 去重
    with _lock:
        if message_id in _processed:
            logger.info("重复消息跳过: %s", message_id)
            return {"code": 0}
        _processed.add(message_id)
        if len(_processed) > 1000:
            _processed.clear()

    if msg_type != "text":
        logger.info("非文本消息跳过: %s", msg_type)
        return {"code": 0}

    try:
        msg_content = json.loads(message.get("content", "{}"))
        text = msg_content.get("text", "").strip()
    except Exception as e:
        logger.error("内容解析失败: %s", e)
        return {"code": 0}

    logger.info("消息内容: %s", text[:80])

    if not text:
        return {"code": 0}

    sender = event.get("sender", {}).get("sender_id", {}).get("open_id", "unknown")

    thread = threading.Thread(
        target=_safe_handle,
        args=(message_id, text, sender),
        daemon=True,
    )
    thread.start()
    return {"code": 0}


def _safe_handle(message_id, text, sender):
    logger.info("线程开始处理: %s", text[:40])
    try:
        handle_message(message_id, text, sender)
        logger.info("线程处理完成")
    except Exception as e:
        logger.error("处理消息异常: %s", e, exc_info=True)
        try:
            from feishu_bot.client import reply_message
            reply_message(message_id, f"⚠️ 系统错误: {str(e)[:80]}")
        except Exception as e2:
            logger.error("回复错误也失败: %s", e2)


@app.get("/health")
def health():
    return {"status": "ok"}
