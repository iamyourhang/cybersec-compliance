"""
collector/engine.py
核心采集引擎 v2.0 - 分层扫描 + 多模型主备 + 变更对比入库
"""
from __future__ import annotations
import logging, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from collector.parsers.compliance_parser import parse_entry_list, parse_incremental_check
from collector.parsers.validator import filter_entries
from collector.parsers.prompts import (
    get_system_prompt,
    build_regulation_scan_prompt,
    build_certification_scan_prompt,
    build_standard_scan_prompt,
    build_country_scan_prompt,
    build_incremental_check_prompt,
)
from collector.providers.base import ProviderManager, BaseProvider
from database.connection import get_cursor
from database.repository import ComplianceRepository, ChangeLogRepository, compute_diff

logger = logging.getLogger(__name__)


@dataclass
class UpdateStats:
    task_type: str = "full_update"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_countries: int = 0
    processed_countries: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        elapsed = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        return (
            f"✅ {self.task_type} 完成 | 国家={self.processed_countries}/{self.total_countries} | "
            f"新增={self.created_count} 更新={self.updated_count} 跳过={self.skipped_count} "
            f"失败={self.error_count} | 耗时={elapsed:.0f}s"
        )


class CollectorEngine:
    """分层扫描采集引擎：每个国家分三轮（法规/认证/标准）各自搜索，结果合并入库"""

    _INTER_COUNTRY_DELAY = 3
    _INTER_ROUND_DELAY = 2
    _INTER_RECORD_DELAY = 2

    def __init__(self, provider_manager: ProviderManager):
        self.pm = provider_manager

    def full_update(self, country_codes=None, product_codes=None) -> UpdateStats:
        stats = UpdateStats(task_type="full_update")
        countries = self._get_countries(country_codes)
        stats.total_countries = len(countries)
        logger.info("🚀 开始全量更新 [国家=%d, 分层扫描模式]", len(countries))

        for i, country in enumerate(countries, 1):
            code, name = country["code"], country["name_zh"]
            logger.info("--- [%d/%d] 处理: %s (%s) ---", i, stats.total_countries, name, code)
            try:
                created, updated, skipped = self._update_country_layered(code, name)
                stats.created_count += created
                stats.updated_count += updated
                stats.skipped_count += skipped
                stats.processed_countries += 1
            except Exception as e:
                msg = f"{code}: {e}"
                logger.error("❌ %s 失败: %s", code, e, exc_info=True)
                stats.error_count += 1
                stats.errors.append(msg)
            if i < stats.total_countries:
                time.sleep(self._INTER_COUNTRY_DELAY)

        logger.info(stats.summary())
        return stats

    def _update_country_layered(self, country_code: str, country_name: str) -> Tuple[int, int, int]:
        """分三轮扫描：法规 → 认证 → 标准，每轮结果实时入库"""
        existing = ComplianceRepository.list_by_country(
            country_code,
            status="active",
            include_quarantined=True,
        )
        existing_names = [r["name"] for r in existing]
        existing_by_name = {r["name"]: dict(r) for r in existing}

        total_created = total_updated = total_skipped = 0

        rounds = [
            ("法规", build_regulation_scan_prompt(country_code, country_name, existing_names)),
            ("认证", build_certification_scan_prompt(country_code, country_name, existing_names)),
            ("标准", build_standard_scan_prompt(country_code, country_name, existing_names)),
        ]

        for round_name, prompt in rounds:
            logger.info("  📋 第%s轮扫描: %s", round_name, country_name)
            try:
                entries = self._call_provider(prompt, country_code)
                if not entries:
                    logger.info("  ⚠️  %s轮无返回数据", round_name)
                    continue

                # 过滤掉已有记录中本轮不应覆盖的类型（减少噪音）
                type_map = {"法规": "regulation", "认证": "certification", "标准": "standard"}
                expected_type = type_map.get(round_name)
                filtered = [e for e in entries if e.get("entry_type") == expected_type]
                noise = len(entries) - len(filtered)
                if noise > 0:
                    logger.debug("  过滤掉 %d 条类型不符的记录", noise)

                c, u, s = self._upsert_entries(filtered, existing_by_name, country_name)
                total_created += c
                total_updated += u
                total_skipped += s

                # 更新 existing_names 避免下轮重复
                for e in filtered:
                    if e["name"] not in existing_names:
                        existing_names.append(e["name"])

            except Exception as e:
                logger.error("  %s轮扫描失败: %s", round_name, e, exc_info=True)

            time.sleep(self._INTER_ROUND_DELAY)

        logger.info("  %s 完成: 新增=%d 更新=%d 跳过=%d", country_name, total_created, total_updated, total_skipped)
        return total_created, total_updated, total_skipped

    def _call_provider(self, prompt: str, country_code: str) -> List[Dict[str, Any]]:
        """调用主力 Provider，失败自动降级"""
        system = get_system_prompt()
        response = self.pm.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.2,
            max_tokens=8000,
            enable_web_search=True,
            require_web_search=True,
        )
        entries, errors = parse_entry_list(
            ai_output=response.content,
            source_name=f"{response.provider_name}/{response.model}",
            country_code=country_code,
        )
        logger.info("    ✅ Provider=%s 返回%d条，解析失败%d条，耗时%.1fs",
                    response.provider_name, len(entries), len(errors), response.latency_ms/1000)
        return entries

    # 全量更新时不覆盖的字段（人工数据保护）
    _PROTECTED_FIELDS = {
        "name", "effective_date", "transition_end_date", "issuing_body",
        "official_url", "requirements", "applicable_products",
        "technical_standards", "regulation_basis", "remarks",
        "scope_description", "assessment_procedure", "testing_bodies",
    }

    def _upsert_entries(self, entries, existing_by_name, country_name) -> Tuple[int, int, int]:
        created = updated = skipped = 0
        for entry in entries:
            try:
                name = entry["name"]
                if name in existing_by_name:
                    old_rec = existing_by_name[name]
                    rid = str(old_rec["id"])

                    # 规则1：verified=True 的记录，AI不覆盖任何字段
                    if old_rec.get("verified"):
                        ComplianceRepository.update_last_checked([rid])
                        skipped += 1
                        logger.debug("    🔒 跳过（已核实）: %s", name[:60])
                        continue

                    # 规则2：只更新 AI 新数据中非空、且原记录为空的字段
                    # 以及允许更新的非保护字段
                    safe_update = {}
                    for field, new_val in entry.items():
                        if field in ("id", "created_at", "version", "verified", "data_source"):
                            continue
                        old_val = old_rec.get(field)
                        # 保护字段：原记录有值则不覆盖
                        if field in self._PROTECTED_FIELDS and not _is_empty(old_val):
                            continue
                        # 非保护字段：AI可以更新（如 confidence_score, last_checked, data_source）
                        if not _is_empty(new_val):
                            safe_update[field] = new_val

                    if safe_update:
                        diff = compute_diff(old_rec, {**old_rec, **safe_update})
                        if diff["changed_fields"]:
                            ComplianceRepository.update(rid, safe_update)
                            ChangeLogRepository.record_change(
                                record_id=rid, change_type="updated",
                                old_value=old_rec, new_value=safe_update,
                                changed_fields=diff["changed_fields"],
                                diff_summary=_fmt_diff(diff["diff"]),
                                data_source=entry.get("data_source"),
                            )
                            updated += 1
                            logger.info("    ✏️  补充更新: %s [%d字段]", name[:60], len(diff["changed_fields"]))
                        else:
                            ComplianceRepository.update_last_checked([rid])
                            skipped += 1
                    else:
                        ComplianceRepository.update_last_checked([rid])
                        skipped += 1

                else:
                    new_id = ComplianceRepository.create(entry)
                    ChangeLogRepository.record_change(
                        record_id=new_id, change_type="created",
                        old_value=None, new_value=entry,
                        data_source=entry.get("data_source"),
                    )
                    existing_by_name[name] = {**entry, "id": new_id}
                    created += 1
                    logger.info("    ➕ 新增: %s", name[:70])
            except Exception as e:
                logger.error("    入库失败 [%s]: %s", entry.get("name","?")[:50], e, exc_info=True)
        return created, updated, skipped

    def incremental_check(self, priority=None, country_codes=None, limit_per_country=10) -> UpdateStats:
        stats = UpdateStats(task_type="incremental_check")
        records = self._get_records_to_check(priority, country_codes, limit_per_country)
        stats.total_countries = len(set(r["country_code"] for r in records))
        logger.info("🔍 增量检查 [记录=%d, 国家=%d]", len(records), stats.total_countries)

        providers = self.pm._providers
        for i, record in enumerate(records, 1):
            provider = providers[i % len(providers)]
            try:
                changed = self._check_single_record(record, provider)
                if changed: stats.updated_count += 1
                else: stats.skipped_count += 1
            except Exception as e:
                logger.error("检查失败 [%s]: %s", record["name"][:50], e)
                stats.error_count += 1
            if i < len(records):
                time.sleep(self._INTER_RECORD_DELAY)

        stats.processed_countries = stats.total_countries
        logger.info(stats.summary())
        return stats

    def _check_single_record(self, record, provider: BaseProvider) -> bool:
        prompt = build_incremental_check_prompt(record)
        resp = provider.chat(
            messages=[
                {"role": "system", "content": get_system_prompt()},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1, max_tokens=1000,
            enable_web_search=provider.supports_web_search,
        )
        result = parse_incremental_check(resp.content)
        rid = str(record["id"])
        if result["has_changes"] and result.get("updated_fields"):
            ComplianceRepository.update(rid, result["updated_fields"])
            ChangeLogRepository.record_change(
                record_id=rid, change_type="updated",
                old_value=dict(record), new_value=result["updated_fields"],
                changed_fields=list(result["updated_fields"].keys()),
                diff_summary=result.get("change_summary"),
                data_source=provider.name,
            )
            logger.info("🔔 变更: %s — %s", record["name"][:50], result.get("change_summary"))
            return True
        else:
            ComplianceRepository.update_last_checked([rid])
            return False

    def _get_countries(self, codes=None):
        with get_cursor() as cur:
            if codes:
                cur.execute("SELECT code, name_zh, priority FROM countries WHERE code=ANY(%s) AND enabled=TRUE ORDER BY priority", (codes,))
            else:
                cur.execute("SELECT code, name_zh, priority FROM countries WHERE enabled=TRUE ORDER BY priority")
            return list(cur.fetchall())

    def _get_records_to_check(self, priority, country_codes, limit_per_country):
        with get_cursor() as cur:
            sql = "SELECT ck.* FROM compliance_knowledge ck JOIN countries c ON ck.country_code=c.code WHERE ck.status='active' AND c.enabled=TRUE"
            params = []
            if priority: sql += " AND c.priority=%s"; params.append(priority)
            if country_codes: sql += " AND ck.country_code=ANY(%s)"; params.append(country_codes)
            sql += " ORDER BY ck.last_checked ASC NULLS FIRST LIMIT %s"
            params.append(limit_per_country * 50)
            cur.execute(sql, params)
            return list(cur.fetchall())


def _fmt_diff(diff):
    if not diff: return "无变更"
    parts = [f"{f}: '{str(c.get('old',''))[:30]}'->'{str(c.get('new',''))[:30]}'" for f, c in list(diff.items())[:4]]
    s = "; ".join(parts)
    return s + (f" 等{len(diff)}个字段" if len(diff) > 4 else "")
