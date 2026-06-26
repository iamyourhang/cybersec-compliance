"""
notifier/feishu.py
飞书 Webhook 通知 - 支持文本、富文本卡片、预警消息
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from base64 import b64encode
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import requests

from config.settings import get_settings

logger = logging.getLogger(__name__)
RECENT_AI_DISCOVERY_DAYS = 7
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass
class AlertMessage:
    """预警消息数据结构"""
    title: str
    content: str
    level: str = "warning"   # info / warning / danger
    country: Optional[str] = None
    record_name: Optional[str] = None
    effective_date: Optional[str] = None
    days_until: Optional[int] = None
    source_url: Optional[str] = None


class FeishuNotifier:
    """飞书群机器人 Webhook 通知器"""

    _COLOR_MAP = {
        "info":    "turquoise",
        "warning": "orange",
        "danger":  "red",
        "success": "green",
    }
    _RATE_LIMIT_ERROR_CODES = {11232}
    _RATE_LIMIT_BACKOFF_SECONDS = (5, 30, 90)

    def __init__(self, webhook_url: str, secret: str = ""):
        self._url = webhook_url
        self._secret = secret
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json; charset=utf-8"})
        self._rate_limit_backoffs = self._RATE_LIMIT_BACKOFF_SECONDS

    # --------------------------------------------------------
    # 公共方法
    # --------------------------------------------------------

    def send_text(self, text: str) -> bool:
        """发送纯文本消息"""
        payload = {"msg_type": "text", "content": {"text": text}}
        return self._send(payload)

    def send_alert(self, alert: AlertMessage) -> bool:
        """发送预警卡片消息"""
        color = self._COLOR_MAP.get(alert.level, "orange")
        header_title = {
            "info":    "📋 合规信息通知",
            "warning": "⚠️ 合规预警",
            "danger":  "🚨 紧急合规预警",
            "success": "✅ 合规更新",
        }.get(alert.level, "合规通知")

        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{alert.title}**",
                },
            }
        ]

        # 详情字段
        fields = []
        if alert.country:
            fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**国家/地区**\n{alert.country}"}})
        if alert.effective_date:
            fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**生效日期**\n{alert.effective_date}"}})
        if alert.days_until is not None:
            days_str = f"**今日生效**" if alert.days_until == 0 else f"还有 **{alert.days_until}** 天"
            fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**倒计时**\n{days_str}"}})
        if alert.source_url:
            fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**官方原文**\n{_format_source_link(alert.source_url)}"}})

        if fields:
            elements.append({"tag": "field_set", "fields": fields})

        if alert.content:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": alert.content},
            })

        elements.append({"tag": "hr"})
        elements.append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": "网安合规助手 · 自动通知"}],
        })

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": header_title},
                    "template": color,
                },
                "elements": elements,
            },
        }
        return self._send(payload)

    def send_weekly_report_card(
        self,
        total_records: int,
        country_count: int,
        candidate_this_week: int,
        verified_this_week: int,
        source_artifacts_this_week: int,
        quarantined_this_week: int,
        upcoming_alerts: List[Dict],
        report_url: Optional[str] = None,
    ) -> bool:
        """发送周报摘要卡片"""
        elements = [
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**知识库总条数**\n{total_records}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**覆盖国家/地区**\n{country_count}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**本周候选**\n{candidate_this_week}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**本周核验通过**\n{verified_this_week}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**本周原文工件**\n{source_artifacts_this_week}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**本周隔离**\n{quarantined_this_week}"}},
                ],
            },
            {"tag": "hr"},
        ]

        # 即将生效预警
        if upcoming_alerts:
            alert_lines = []
            for a in upcoming_alerts[:8]:
                days = a.get("days_until_effective", "?")
                days_str = "**今日生效**" if days == 0 else f"{days}天后"
                milestone = a.get("milestone_label_zh") or "生效/适用节点"
                alert_lines.append(
                    f"• {a.get('country_name','?')} · {a.get('name','?')} · {milestone} · "
                    f"{days_str} · {_format_source_link(a.get('official_url'))}"
                )
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**⏰ 近30天即将生效**\n" + "\n".join(alert_lines),
                },
            })
            elements.append({"tag": "hr"})

        # 报告下载链接
        if report_url:
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "📥 下载完整 Excel 报告"},
                    "url": report_url,
                    "type": "primary",
                }],
            })

        elements.append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": "网安合规助手 · 每周一 09:00 自动发送"}],
        })

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "📊 网安合规周报"},
                    "template": "blue",
                },
                "elements": elements,
            },
        }
        return self._send(payload)

    def send_frontline_digest_card(
        self,
        new_sources: List[Dict],
        new_verified: List[Dict],
        upcoming_by_window: Dict[int, List[Dict]],
        ai_discovery_stats: Optional[Dict[str, Any]] = None,
        ai_discovery_candidates: Optional[List[Dict[str, Any]]] = None,
        official_dynamics: Optional[List[Dict[str, Any]]] = None,
        lookback_hours: int = 24,
    ) -> bool:
        """发送网安合规动态：官方候选、动态参考、正式入库和未来适用节点。"""
        weekly_mode = lookback_hours >= 24 * 7
        digest_title = "每周网安合规动态" if weekly_mode else "今日网安合规早报"
        digest_period = "本周" if weekly_mode else "今日"
        source_limit = 20 if weekly_mode else 8
        candidate_limit = 20 if weekly_mode else 8
        dynamic_limit = 30 if weekly_mode else 12
        verified_limit = 20 if weekly_mode else 8
        recent_ai_candidates, historical_ai_candidates, unknown_date_ai_candidates = _split_ai_candidates_by_source_date(
            ai_discovery_candidates or []
        )
        display_ai_candidates = recent_ai_candidates
        official_dynamics = _filter_recent_dated_items(official_dynamics or [])
        candidate_count = len(display_ai_candidates)
        source_count = len(new_sources or [])
        verified_count = len(new_verified)
        dynamics_count = len(official_dynamics)
        window_30_count = len(upcoming_by_window.get(30, []))
        schedule_summary = _format_compact_schedule(upcoming_by_window)
        lead = _format_frontline_digest_lead(
            source_count=source_count,
            candidate_count=candidate_count,
            dynamics_count=dynamics_count,
            verified_count=verified_count,
            window_30_count=window_30_count,
            period_label=digest_period,
        )
        collection_status = _format_collection_status(ai_discovery_stats or {}, digest_label=digest_title)
        elements: List[Dict[str, Any]] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{digest_period}看点**\n{lead}",
                },
            },
            {"tag": "hr"},
        ]

        if collection_status:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": collection_status},
            })
            elements.append({"tag": "hr"})

        if new_sources:
            lines = _format_grouped_candidate_lines(new_sources, limit=source_limit)
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**🧭 官方源监测（{source_count}条）**\n" + lines},
            })
            elements.append({"tag": "hr"})

        if ai_discovery_stats and int(ai_discovery_stats.get("candidate_count") or 0) > 0:
            candidate_block = _format_grouped_candidate_lines(display_ai_candidates, limit=candidate_limit)
            if not candidate_block:
                candidate_block = "• 暂无可展示的候选原文链接，请到后台候选列表查看。"
            content = (
                f"**🔎 待核验官方线索（{candidate_count}条）**\n"
                f"{candidate_block}"
            )
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": content},
            })
            elements.append({"tag": "hr"})

        if official_dynamics:
            lines = _format_news_digest_lines(official_dynamics, limit=dynamic_limit)
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**📰 网安合规动态（{dynamics_count}条）**\n"
                        + lines
                    ),
                },
            })
            elements.append({"tag": "hr"})

        if new_verified:
            lines = []
            for item in new_verified[:verified_limit]:
                country = _format_country_label(item)
                mandatory = item.get("mandatory") or "未标注"
                lines.append(
                    f"• {country} · {item.get('name') or '?'} · {mandatory} · "
                    f"{_format_source_link(item.get('official_url'))}"
                )
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**✅ {digest_period}已验证入库（{verified_count}条）**\n" + "\n".join(lines)},
            })
            elements.append({"tag": "hr"})

        if schedule_summary:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**⏰ 合规日程**\n" + schedule_summary},
            })

        elements.append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": "网安合规助手 · 正式导出/问答/预警只使用 verified 官方证据"}],
        })

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": digest_title},
                    "template": "turquoise",
                },
                "elements": elements,
            },
        }
        return self._send(payload)

    # --------------------------------------------------------
    # 内部方法
    # --------------------------------------------------------

    def _send(self, payload: Dict[str, Any]) -> bool:
        """发送请求，含签名（如配置了 secret）"""
        max_attempts = len(self._rate_limit_backoffs) + 1
        for attempt in range(max_attempts):
            send_payload = dict(payload)
            if self._secret:
                timestamp, sign = self._generate_sign()
                send_payload["timestamp"] = timestamp
                send_payload["sign"] = sign

            try:
                resp = self._session.post(
                    self._url,
                    data=json.dumps(send_payload, ensure_ascii=False).encode("utf-8"),
                    timeout=15,
                )
                resp.raise_for_status()
                result = resp.json()
                if result.get("code", 0) == 0:
                    logger.debug("飞书通知发送成功")
                    return True

                if self._should_retry_rate_limit(result=result, attempt=attempt):
                    self._sleep_before_retry(attempt, result)
                    continue

                logger.error("飞书 API 返回错误: %s", result)
                return False
            except requests.RequestException as e:
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                if status_code == 429 and self._should_retry_rate_limit(result=None, attempt=attempt):
                    self._sleep_before_retry(attempt, {"http_status": status_code, "error": str(e)})
                    continue
                logger.error("飞书通知发送失败: %s", e)
                return False

        return False

    def _should_retry_rate_limit(self, result: Optional[Dict[str, Any]], attempt: int) -> bool:
        if attempt >= len(self._rate_limit_backoffs):
            return False
        if result is None:
            return True
        return int(result.get("code") or 0) in self._RATE_LIMIT_ERROR_CODES

    def _sleep_before_retry(self, attempt: int, result: Dict[str, Any]) -> None:
        delay = self._rate_limit_backoffs[attempt]
        logger.warning("飞书发送触发频控，%s 秒后重试: %s", delay, result)
        time.sleep(delay)

    def _generate_sign(self) -> tuple[str, str]:
        """生成飞书 Webhook 签名"""
        timestamp = str(int(time.time()))
        sign_str = f"{timestamp}\n{self._secret}"
        sign = b64encode(
            hmac.new(sign_str.encode("utf-8"), digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        return timestamp, sign


def get_notifier() -> Optional[FeishuNotifier]:
    """获取飞书通知器，未配置 Webhook 时返回 None"""
    settings = get_settings()
    url = settings.feishu.webhook_url
    if not url:
        logger.warning("飞书 Webhook URL 未配置，通知功能不可用")
        return None
    return FeishuNotifier(webhook_url=url, secret=settings.feishu.webhook_secret)


def _format_source_link(url: Optional[str], label: str = "官方原文") -> str:
    if not url:
        return "官方原文链接缺失"
    text = str(url).strip()
    if not text.startswith(("http://", "https://")):
        return "官方原文链接缺失"
    return f"[{label}]({text})"


def _coerce_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text[:32], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _split_ai_candidates_by_source_date(
    candidates: List[Dict[str, Any]],
    today: Optional[date] = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    today = today or date.today()
    cutoff = today - timedelta(days=RECENT_AI_DISCOVERY_DAYS)
    recent: List[Dict[str, Any]] = []
    historical: List[Dict[str, Any]] = []
    unknown: List[Dict[str, Any]] = []
    for item in candidates:
        published = _coerce_date(item.get("published_date"))
        if not published:
            unknown.append(item)
        elif published >= cutoff:
            recent.append(item)
        else:
            historical.append(item)
    return recent, historical, unknown


def _filter_recent_dated_items(
    items: List[Dict[str, Any]],
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    today = today or date.today()
    cutoff = today - timedelta(days=RECENT_AI_DISCOVERY_DAYS)
    result: List[Dict[str, Any]] = []
    for item in items:
        published = _coerce_date(item.get("published_date"))
        if published and published >= cutoff:
            result.append(item)
    return result


def _format_candidate_line(item: Dict[str, Any], date_label: Optional[str] = None) -> str:
    country = _format_country_label(item)
    published = _coerce_date(item.get("published_date"))
    if date_label is None:
        date_label = f"发布日期：{published.isoformat()}" if published else "发布日期待核验"
    return (
        f"• {country} · {_format_display_title(item)} · {date_label} · "
        f"{_format_source_link(item.get('artifact_url') or item.get('source_url'))}"
    )


def _format_entry_type(value: Any) -> str:
    text = str(value or "").lower()
    if text == "regulation":
        return "法律法规"
    if text == "certification":
        return "认证"
    if text == "standard":
        return "标准"
    return "其他"


def _format_country_name(item: Dict[str, Any]) -> str:
    code = str(item.get("country_code") or "").upper()
    if code == "TW":
        return "中国台湾"
    return str(item.get("country_name") or code or "?")


def _format_country_label(item: Dict[str, Any]) -> str:
    code = str(item.get("country_code") or "?").upper()
    return f"{_format_country_name(item)}({code})"


def _format_candidate_line_without_country(item: Dict[str, Any], date_label: Optional[str] = None) -> str:
    published = _coerce_date(item.get("published_date"))
    if date_label is None:
        date_label = f"发布日期：{published.isoformat()}" if published else "发布日期待核验"
    line = (
        f"• {_format_display_title(item)} · {date_label} · "
        f"{_format_source_link(item.get('artifact_url') or item.get('source_url'))}"
    )
    summary = _format_display_summary(item)
    if summary:
        line += f"\n  说明：{summary}"
    return line


def _format_grouped_candidate_lines(items: List[Dict[str, Any]], limit: int = 8) -> str:
    groups: "OrderedDict[tuple[str, str], list[Dict[str, Any]]]" = OrderedDict()
    for item in items[:limit]:
        country = _format_country_label(item)
        entry_type = _format_entry_type(item.get("entry_type"))
        groups.setdefault((country, entry_type), []).append(item)

    lines: List[str] = []
    for (country, entry_type), group_items in groups.items():
        lines.append(f"**{country} · {entry_type}**")
        lines.extend(_format_candidate_line_without_country(item) for item in group_items)
    return "\n".join(lines)


def _format_frontline_digest_lead(
    *,
    source_count: int,
    candidate_count: int,
    dynamics_count: int,
    verified_count: int,
    window_30_count: int,
    period_label: str = "今日",
) -> str:
    highlights: List[str] = []
    if candidate_count:
        highlights.append(f"{candidate_count}条待核验官方线索")
    if dynamics_count:
        highlights.append(f"{dynamics_count}条网安合规动态")
    if source_count:
        highlights.append(f"{source_count}条官方源监测")

    if highlights:
        if len(highlights) == 1:
            lead = f"{period_label}监测重点为{highlights[0]}。"
        else:
            lead = f"{period_label}监测重点集中在{'、'.join(highlights[:-1])}和{highlights[-1]}。"
    else:
        lead = f"{period_label}暂未发现新的官方源、待核验线索或网安合规动态。"

    if verified_count:
        lead += f" 正式知识库新增{verified_count}条已验证入库记录。"
    else:
        lead += " 正式知识库暂无新增已验证入库记录。"

    if window_30_count:
        lead += f" 近期日程中有{window_30_count}个30天内适用节点需要关注。"
    else:
        lead += " 30天内暂无紧急适用节点。"

    lead += " 以下内容均保留官方原文链接，便于追溯。"
    return lead


def _format_collection_status(ai_discovery_stats: Dict[str, Any], digest_label: str = "今日早报") -> str:
    latest_status = str(ai_discovery_stats.get("latest_status") or "").strip()
    failed_count = int(ai_discovery_stats.get("failed_run_count") or 0)
    if latest_status != "failed" and failed_count <= 0:
        return ""
    error = _sanitize_collection_error(str(ai_discovery_stats.get("latest_error") or ""))
    lines = [
        "**⚠️ 采集状态**",
        f"• AI 官方源发现任务未完成，{digest_label}可能不完整；这不是“确认无新增”。",
    ]
    if error:
        lines.append(f"• 原因：{error}")
    lines.append("• 处理：请检查内置 AI 通道额度/可用性，恢复后重新运行采集。")
    return "\n".join(lines)


def _sanitize_collection_error(error: str) -> str:
    text = (error or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if "insufficient_user_quota" in lowered or "用户额度不足" in text or "quota" in lowered:
        return "内置 AI 通道额度不足。"
    if "timeout" in lowered or "timed out" in lowered:
        return "联网搜索或模型调用超时。"
    if "403" in text:
        return "内置 AI 通道返回 403，可能是额度、权限或模型不可用。"
    return text[:180]


def _format_news_digest_lines(items: List[Dict[str, Any]], limit: int = 12) -> str:
    lines: List[str] = []
    for item in items[:limit]:
        country = _format_country_label(item)
        entry_type = _format_entry_type(item.get("entry_type"))
        published = _coerce_date(item.get("published_date"))
        date_label = published.isoformat() if published else "日期待核验"
        title = _format_display_title(item)
        summary = _format_display_summary(item)
        link = _format_source_link(item.get("artifact_url") or item.get("source_url"))
        block = [
            f"• **{title}**",
            f"  {country} · {entry_type} · {date_label} · {link}",
        ]
        if summary:
            block.append(f"  摘要：{summary}")
        lines.append("\n".join(block))
    return "\n".join(lines)


def _format_compact_schedule(upcoming_by_window: Dict[int, List[Dict[str, Any]]]) -> str:
    if not upcoming_by_window:
        return ""

    counts = "；".join(
        f"{days}天内 {len(upcoming_by_window.get(days) or [])}"
        for days in sorted(upcoming_by_window)
    )
    nearest: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for days in sorted(upcoming_by_window):
        for item in upcoming_by_window.get(days) or []:
            key = (
                str(item.get("id") or item.get("compliance_id") or item.get("name") or ""),
                str(item.get("milestone_key") or item.get("milestone_label_zh") or ""),
                str(item.get("effective_date") or item.get("milestone_date") or item.get("days_until_effective") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            nearest.append(item)

    nearest.sort(key=lambda row: int(row.get("days_until_effective") or 999999))
    lines = [f"• 窗口概览：{counts}"]
    if nearest:
        preview = []
        for item in nearest[:3]:
            country = _format_country_name(item)
            name = item.get("name") or "?"
            label = item.get("milestone_label_zh") or "生效/适用节点"
            days = item.get("days_until_effective", "?")
            preview.append(
                f"{country} · {name} · {label}（{days}天） · {_format_source_link(item.get('official_url'))}"
            )
        lines.append("• 最近节点：" + "；".join(preview))
    return "\n".join(lines)


def _format_ai_candidate_groups(
    *,
    recent_ai_candidates: List[Dict[str, Any]],
    historical_ai_candidates: List[Dict[str, Any]],
    unknown_date_ai_candidates: List[Dict[str, Any]],
) -> str:
    blocks: List[str] = []
    if recent_ai_candidates:
        blocks.append("**候选原文链接：AI近期新动态**\n" + _format_grouped_candidate_lines(recent_ai_candidates, limit=5))
    if historical_ai_candidates:
        blocks.append("**候选原文链接：AI历史补库线索**\n" + _format_grouped_candidate_lines(historical_ai_candidates, limit=5))
    if unknown_date_ai_candidates:
        blocks.append("**候选原文链接：AI日期待核验线索**\n" + _format_grouped_candidate_lines(unknown_date_ai_candidates, limit=5))
    if not blocks:
        return "**候选原文链接**\n• 暂无可展示的候选原文链接，请到后台候选列表查看。"
    return "\n".join(blocks)


def _format_display_title(item: Dict[str, Any]) -> str:
    original = str(item.get("title") or item.get("name") or "?").strip() or "?"
    translated = _pick_translated_text(
        item,
        "title_zh",
        "name_zh",
        "source_payload.raw_candidate.title_zh",
        "source_payload.raw_candidate.name_zh",
    )
    if not translated:
        translated = _pick_from_translations(
            item,
            "title",
            "name",
            "source_payload.raw_candidate.title",
        )
    if not translated or translated == original:
        return original
    if CJK_RE.search(translated) and not CJK_RE.search(original):
        return f"{translated}（原文：{original}）"
    return translated


def _format_display_summary(item: Dict[str, Any]) -> str:
    return _pick_translated_text(
        item,
        "summary_zh",
        "source_payload.raw_candidate.summary_zh",
        "source_payload.raw_candidate.summary",
        "source_payload.ai_reason",
        "source_payload.cyber_product_relevance_reason",
    )


def _pick_translated_text(item: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    translations = item.get("translations")
    if isinstance(translations, dict):
        for key in keys:
            value = translations.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    payload = _coerce_payload_dict(item.get("source_payload"))
    for key in keys:
        if not key.startswith("source_payload."):
            continue
        value = _get_nested(payload, key.removeprefix("source_payload."))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _pick_from_translations(item: Dict[str, Any], *keys: str) -> str:
    translations = item.get("translations")
    if not isinstance(translations, dict):
        return ""
    for key in keys:
        value = translations.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _coerce_payload_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _get_nested(data: Dict[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current
