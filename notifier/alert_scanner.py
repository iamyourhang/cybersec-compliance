"""
notifier/alert_scanner.py
预警扫描器 - 检查生效日期预警 + 新法规变动通知
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Sequence
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse

from database.connection import get_cursor, get_connection
from database.repository import (
    ComplianceLifecycleRepository,
    source_record_not_known_filter_sql,
)
from collector.discovery.service import is_vulnerability_advisory_not_compliance
from notifier.feishu import AlertMessage, FeishuNotifier, get_notifier

logger = logging.getLogger(__name__)
DEFAULT_UPCOMING_WINDOWS = (30, 90, 180, 360)
FRONTLINE_RECENT_SOURCE_DAYS = 7
DIGEST_LINK_PROBE_TIMEOUT_SECONDS = 8


def _filter_reachable_digest_rows(rows: List[Dict], *, bucket: str) -> List[Dict]:
    """Filter only definite bad links from the daily brief.

    Server-side reachability is not truth: WAF, Cloudflare, DNS, TLS and
    regional network differences can block the server while the link is valid
    for users. We only drop deterministic 404/410/invalid links or rows that
    carry an explicit manual digest suppression marker.
    """
    filtered: List[Dict] = []
    for row in rows:
        if is_vulnerability_advisory_not_compliance(_digest_row_topic_text(row)):
            logger.info(
                "日报剔除漏洞/CVE通告记录 [%s]: %s",
                bucket,
                row.get("title") or row.get("name") or row.get("id"),
            )
            continue
        if _has_digest_suppression(row):
            logger.info(
                "日报剔除人工标记不展示记录 [%s]: %s",
                bucket,
                row.get("title") or row.get("name") or row.get("id"),
            )
            continue
        url = _digest_row_url(row)
        if not url:
            logger.info("日报剔除无原文链接记录 [%s]: %s", bucket, row.get("title") or row.get("name") or row.get("id"))
            continue
        status = _probe_digest_link(url)
        if status == "permanent_unreachable":
            logger.info(
                "日报剔除确定性坏链 [%s]: %s · %s",
                bucket,
                row.get("title") or row.get("name") or row.get("id"),
                url,
            )
            continue
        if status == "server_unverified":
            logger.info(
                "日报保留服务端未能确认链接 [%s]: %s · %s",
                bucket,
                row.get("title") or row.get("name") or row.get("id"),
                url,
            )
        filtered.append(row)
    return filtered


def _digest_row_url(row: Dict) -> str:
    return str(row.get("artifact_url") or row.get("source_url") or row.get("official_url") or "").strip()


def _digest_row_topic_text(row: Dict) -> str:
    payload = row.get("source_payload") or {}
    raw = payload.get("raw_candidate") if isinstance(payload, dict) and isinstance(payload.get("raw_candidate"), dict) else {}
    return " ".join(
        str(value or "")
        for value in (
            row.get("title"),
            row.get("name"),
            row.get("source_url"),
            row.get("artifact_url"),
            row.get("official_url"),
            row.get("entry_type"),
            payload.get("ai_reason") if isinstance(payload, dict) else None,
            payload.get("cyber_product_relevance_reason") if isinstance(payload, dict) else None,
            raw.get("title"),
            raw.get("title_zh"),
            raw.get("summary"),
            raw.get("summary_zh"),
        )
    )


def _has_digest_suppression(row: Dict) -> bool:
    payload = row.get("source_payload") or {}
    if not isinstance(payload, dict):
        return False
    suppression = payload.get("digest_suppression")
    return isinstance(suppression, dict) and bool(suppression.get("reason"))


def _is_digest_link_reachable(url: str) -> bool:
    return _probe_digest_link(url) == "reachable"


def _probe_digest_link(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "permanent_unreachable"

    req = urlrequest.Request(
        url,
        method="GET",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Range": "bytes=0-2047",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=DIGEST_LINK_PROBE_TIMEOUT_SECONDS) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            if status in {404, 410}:
                return "permanent_unreachable"
            if status < 200 or status >= 400:
                return "server_unverified"
            resp.read(256)
            return "reachable"
    except urlerror.HTTPError as exc:
        logger.info("日报原文链接 HTTP 探测结果: %s -> %s", url, exc.code)
        if exc.code in {404, 410}:
            return "permanent_unreachable"
        return "server_unverified"
    except Exception as exc:
        logger.info("日报原文链接探测失败: %s -> %s", url, exc)
        return "server_unverified"


class AlertScanner:
    """预警扫描器，由调度器每日调用"""

    def __init__(self, notifier: Optional[FeishuNotifier] = None):
        self._notifier = notifier or get_notifier()

    def run(self) -> dict:
        """执行全部预警扫描，返回统计"""
        stats = {"effective_date_alerts": 0, "change_alerts": 0, "frontline_digest": 0, "errors": 0}

        if not self._notifier:
            logger.warning("飞书 Notifier 不可用，跳过预警")
            return stats

        try:
            stats["effective_date_alerts"] = self._scan_effective_date_alerts()
        except Exception as e:
            logger.error("生效日期预警扫描失败: %s", e, exc_info=True)
            stats["errors"] += 1

        try:
            stats["change_alerts"] = self._scan_change_alerts()
        except Exception as e:
            logger.error("变动预警扫描失败: %s", e, exc_info=True)
            stats["errors"] += 1

        logger.info(
            "预警扫描完成: 生效日期预警=%d, 变动预警=%d, 早报由独立9点任务发送, 失败=%d",
            stats["effective_date_alerts"], stats["change_alerts"], stats["errors"],
        )
        return stats

    def scan_frontline_digest(
        self,
        lookback_hours: int = 24,
        upcoming_windows: Sequence[int] = DEFAULT_UPCOMING_WINDOWS,
        limit: int = 10,
    ) -> int:
        return self._scan_frontline_digest(lookback_hours=lookback_hours, upcoming_windows=upcoming_windows, limit=limit)

    def _scan_frontline_digest(
        self,
        lookback_hours: int = 24,
        upcoming_windows: Sequence[int] = DEFAULT_UPCOMING_WINDOWS,
        limit: int = 10,
    ) -> int:
        """发送前道闭环摘要：新发现、核验入库、生效窗口。"""
        if not self._notifier:
            return 0

        new_sources = _filter_reachable_digest_rows(
            self._collect_new_source_records(lookback_hours=lookback_hours, limit=limit),
            bucket="official_source",
        )
        new_verified = self._collect_new_verified_records(lookback_hours=lookback_hours, limit=limit)
        upcoming_by_window = self._collect_upcoming_windows(upcoming_windows=upcoming_windows, limit=limit)
        ai_discovery_candidates = _filter_reachable_digest_rows(
            self._collect_ai_discovery_candidates(lookback_hours=lookback_hours, limit=limit),
            bucket="ai_discovery_candidate",
        )
        official_dynamics = _filter_reachable_digest_rows(
            self._collect_official_dynamics(lookback_hours=lookback_hours, limit=limit),
            bucket="official_dynamic",
        )
        ai_discovery_stats = dict(self._collect_ai_discovery_summary(lookback_hours=lookback_hours) or {})
        if ai_discovery_stats:
            ai_discovery_stats["raw_candidate_count"] = ai_discovery_stats.get("candidate_count", 0)
            ai_discovery_stats["candidate_count"] = len(ai_discovery_candidates)
            ai_discovery_stats["reference_count"] = len(official_dynamics)
        discovery_failed = bool(
            (ai_discovery_stats or {}).get("failed_run_count")
            or (ai_discovery_stats or {}).get("latest_status") == "failed"
        )

        has_payload = bool(
            new_sources
            or new_verified
            or any(upcoming_by_window.values())
            or official_dynamics
            or (ai_discovery_stats and ai_discovery_stats.get("candidate_count", 0) > 0)
            or ai_discovery_candidates
            or discovery_failed
        )
        if not has_payload:
            return 0

        success = self._notifier.send_frontline_digest_card(
            new_sources=new_sources,
            new_verified=new_verified,
            upcoming_by_window=upcoming_by_window,
            ai_discovery_stats=ai_discovery_stats,
            ai_discovery_candidates=ai_discovery_candidates,
            official_dynamics=official_dynamics,
            lookback_hours=lookback_hours,
        )
        return 1 if success else 0

    def _collect_new_source_records(self, lookback_hours: int, limit: int) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                f"""
                SELECT sr.id::TEXT AS id,
                       sr.title,
                       sr.country_code,
                       c.name_zh AS country_name,
                       sr.entry_type,
                       sr.source_status,
                       sr.source_url,
                       sr.artifact_url,
                       sr.published_date,
                       sr.created_at,
                       sr.source_payload,
                       os.name AS source_name
                FROM source_records sr
                JOIN countries c ON c.code = sr.country_code
                LEFT JOIN official_sources os ON os.id = sr.official_source_id
                WHERE sr.created_at >= NOW() - (%s * INTERVAL '1 hour')
                  AND sr.source_status = 'candidate'
                  AND sr.published_date IS NOT NULL
                  AND sr.published_date >= CURRENT_DATE - ({FRONTLINE_RECENT_SOURCE_DAYS} * INTERVAL '1 day')
                  AND COALESCE(sr.discovery_method, 'official_source') <> 'ai_weekly_discovery'
                  {source_record_not_known_filter_sql("sr")}
                ORDER BY sr.created_at DESC
                LIMIT %s
                """,
                (lookback_hours, limit),
            )
            return self._attach_source_record_translations([dict(row) for row in cur.fetchall()])

    def _collect_ai_discovery_candidates(self, lookback_hours: int, limit: int) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                f"""
                SELECT sr.id::TEXT AS id,
                       sr.title,
                       sr.country_code,
                       c.name_zh AS country_name,
                       sr.entry_type,
                       sr.source_status,
                       sr.source_url,
                       sr.artifact_url,
                       sr.published_date,
                       sr.created_at,
                       sr.source_payload
                FROM source_records sr
                JOIN countries c ON c.code = sr.country_code
                WHERE sr.created_at >= NOW() - (%s * INTERVAL '1 hour')
                  AND sr.source_status = 'candidate'
                  AND sr.discovery_method = 'ai_weekly_discovery'
                  AND sr.published_date IS NOT NULL
                  AND sr.published_date >= CURRENT_DATE - ({FRONTLINE_RECENT_SOURCE_DAYS} * INTERVAL '1 day')
                  {source_record_not_known_filter_sql("sr")}
                ORDER BY sr.created_at DESC
                LIMIT %s
                """,
                (lookback_hours, limit),
            )
            return self._attach_source_record_translations([dict(row) for row in cur.fetchall()])

    def _collect_official_dynamics(self, lookback_hours: int, limit: int) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                f"""
                SELECT sr.id::TEXT AS id,
                       sr.title,
                       sr.country_code,
                       c.name_zh AS country_name,
                       sr.entry_type,
                       sr.source_status,
                       sr.source_url,
                       sr.artifact_url,
                       sr.published_date,
                       sr.created_at,
                       sr.source_payload
                FROM source_records sr
                JOIN countries c ON c.code = sr.country_code
                WHERE sr.created_at >= NOW() - (%s * INTERVAL '1 hour')
                  AND sr.source_status = 'reference'
                  AND sr.discovery_method = 'ai_weekly_discovery'
                  AND COALESCE(sr.source_payload ->> 'reference_kind', '') = 'official_dynamic'
                  AND sr.published_date IS NOT NULL
                  AND sr.published_date >= CURRENT_DATE - ({FRONTLINE_RECENT_SOURCE_DAYS} * INTERVAL '1 day')
                  {source_record_not_known_filter_sql("sr")}
                ORDER BY sr.created_at DESC
                LIMIT %s
                """,
                (lookback_hours, limit),
            )
            return self._attach_source_record_translations([dict(row) for row in cur.fetchall()])

    def _attach_source_record_translations(self, rows: List[Dict]) -> List[Dict]:
        if not rows:
            return rows
        try:
            from collector.translation.repository import list_translations_for_entities
            from collector.translation.service import attach_translation_fields

            translations = list_translations_for_entities("source_records", [str(row.get("id")) for row in rows])
            if not translations:
                return rows
            return [
                attach_translation_fields(row, translations, entity_id_field="id")
                for row in rows
            ]
        except Exception as exc:
            logger.warning("早报 source_records 翻译读取失败，使用原文标题: %s", exc)
            return rows

    def _collect_new_verified_records(self, lookback_hours: int, limit: int) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT ci.compliance_id::TEXT AS id,
                       ci.name,
                       ci.country_code,
                       c.name_zh AS country_name,
                       ci.entry_type,
                       ci.mandatory,
                       ci.official_url,
                       rc.checked_at
                FROM compliance_index ci
                JOIN review_cases rc ON rc.id = ci.review_case_id
                JOIN countries c ON c.code = ci.country_code
                WHERE rc.checked_at >= NOW() - (%s * INTERVAL '1 hour')
                  AND rc.current_status = 'verified'
                  AND ci.status = 'active'
                  AND ci.authenticity_status = 'verified'
                ORDER BY rc.checked_at DESC
                LIMIT %s
                """,
                (lookback_hours, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def _collect_upcoming_windows(self, upcoming_windows: Sequence[int], limit: int) -> Dict[int, List[Dict]]:
        return {
            int(days): ComplianceLifecycleRepository.get_upcoming_milestones(days=int(days), limit=limit)
            for days in upcoming_windows
        }

    def _collect_ai_discovery_summary(self, lookback_hours: int) -> Dict[str, int]:
        try:
            from collector.discovery.service import AIDiscoveryRunRepository

            return AIDiscoveryRunRepository().latest_summary(lookback_hours=lookback_hours)
        except Exception as exc:
            logger.warning("AI Discovery 摘要读取失败，跳过本次前道通报 AI 段: %s", exc)
            return {}

    def _scan_effective_date_alerts(self) -> int:
        """扫描生效日期预警（30天/7天/当天）"""
        sent_count = 0

        # 获取所有启用的预警规则（生效日期类型）
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM alert_rules WHERE rule_type='effective_date' AND enabled=TRUE ORDER BY days_before DESC"
            )
            rules = list(cur.fetchall())

        for rule in rules:
            days_before = rule["days_before"]
            try:
                count = self._process_effective_date_rule(rule_id=rule["id"], days_before=days_before)
                sent_count += count
            except Exception as e:
                logger.error("规则 %s（%d天）处理失败: %s", rule["name"], days_before, e)

        return sent_count

    def _process_effective_date_rule(self, rule_id: int, days_before: int) -> int:
        """处理单个生效日期预警规则"""
        today = date.today()

        # 计算目标生效日期
        from datetime import timedelta
        target_date = today + timedelta(days=days_before)

        records = ComplianceLifecycleRepository.get_milestones_for_date(target_date, mandatory_only=True)

        sent = 0
        for record in records:
            record_id = str(record["id"])
            # 检查今天是否已发送过
            if self._already_sent(rule_id, record_id):
                continue

            level = "danger" if days_before <= 7 else "warning"
            milestone_label = record.get("milestone_label_zh") or "生效/适用节点"
            days_label = "今日适用" if days_before == 0 else f"距该节点还有 {days_before} 天"
            products_str = "、".join(record.get("applicable_products") or [])

            alert = AlertMessage(
                title=f"【合规预警】{record['name']}",
                content=(
                    f"**{days_label}**\n\n"
                    f"节点：**{milestone_label}**\n\n"
                    f"该法规/认证即将进入新的适用阶段，请确认相关产品已完成合规准备。\n\n"
                    f"**适用产品：** {products_str or '见官方文件'}"
                ),
                level=level,
                country=f"{record['country_name']} ({record['country_code']})",
                record_name=record["name"],
                effective_date=str(record["effective_date"]),
                days_until=days_before,
                source_url=record.get("official_url"),
            )

            success = self._notifier.send_alert(alert)
            self._record_sent(rule_id, record_id, success)
            if success:
                sent += 1
                logger.info("✅ 预警发送: %s [%s天]", record["name"], days_before)

        return sent

    def _scan_change_alerts(self) -> int:
        """扫描近24小时内的新法规/修订/废止变动"""
        with get_cursor() as cur:
            cur.execute(
                """
                WITH events AS (
                    SELECT cl.id::TEXT AS id,
                           cl.change_type::TEXT AS change_type,
                           cl.diff_summary,
                           cl.changed_at,
                           ci.name,
                           ci.country_code,
                           c.name_zh AS country_name,
                           ci.official_url,
                           0 AS source_rank
                    FROM change_log cl
                    JOIN compliance_index ci ON cl.record_id = ci.compliance_id
                    JOIN countries c ON ci.country_code = c.code
                    WHERE cl.changed_at >= NOW() - INTERVAL '24 hours'
                      AND cl.change_type IN ('created', 'deprecated')
                      AND ci.status='active'
                      AND ci.authenticity_status = 'verified'
                    UNION ALL
                    SELECT rc.id::TEXT AS id,
                           'created' AS change_type,
                           '官方证据核验通过，进入正式知识库' AS diff_summary,
                           rc.checked_at AS changed_at,
                           ci.name,
                           ci.country_code,
                           c.name_zh AS country_name,
                           ci.official_url,
                           1 AS source_rank
                    FROM compliance_index ci
                    JOIN review_cases rc ON rc.id = ci.review_case_id
                    JOIN countries c ON ci.country_code = c.code
                    WHERE rc.checked_at >= NOW() - INTERVAL '24 hours'
                      AND rc.current_status='verified'
                      AND ci.status='active'
                      AND ci.authenticity_status = 'verified'
                )
                SELECT id, change_type, diff_summary, changed_at, name, country_code, country_name, official_url
                FROM (
                    SELECT DISTINCT ON (name, country_code)
                           id, change_type, diff_summary, changed_at, name, country_code, country_name, official_url, source_rank
                    FROM events
                    WHERE changed_at IS NOT NULL
                    ORDER BY name, country_code, changed_at DESC, source_rank
                ) latest
                ORDER BY changed_at DESC
                LIMIT 20
                """,
            )
            changes = list(cur.fetchall())

        if not changes:
            return 0

        # 合并发一条摘要
        lines = []
        for ch in changes:
            icon = {"created": "➕", "deprecated": "❌", "updated": "✏️"}.get(ch["change_type"], "•")
            source_link = f"[官方原文]({ch['official_url']})" if ch.get("official_url") else "官方原文链接缺失"
            lines.append(f"{icon} [{ch['country_name']}] {ch['name']} · {source_link}")

        alert = AlertMessage(
            title=f"合规知识库变动通知（共{len(changes)}条）",
            content="\n".join(lines[:10]),
            level="info",
        )
        success = self._notifier.send_alert(alert)
        return len(changes) if success else 0

    def _already_sent(self, rule_id: int, record_id: str) -> bool:
        """检查今天是否已向该记录发送过该规则的预警"""
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM alert_sent_log
                WHERE rule_id = %s AND record_id = %s
                  AND sent_at::DATE = CURRENT_DATE
                """,
                (rule_id, record_id),
            )
            return cur.fetchone() is not None

    def _record_sent(self, rule_id: int, record_id: str, success: bool) -> None:
        """记录预警发送日志"""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO alert_sent_log (rule_id, record_id, success)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (rule_id, record_id, success),
                    )
        except Exception as e:
            logger.error("记录预警发送日志失败: %s", e)
