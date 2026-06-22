#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.connection import get_connection, get_cursor

PRODUCT_REGIME_PATTERN = (
    r"("
    r"certification|scheme|label|labeling|trust mark|common criteria|protection profile|"
    r"niap|cspn|cyber essentials|cyber fundamentals|qcvn|jc-star|jc star|"
    r"technical regulation|conformity|approval|product security|secure[- ]by[- ]design|"
    r"cyber resilience act|products with digital elements|horizontal cybersecurity requirements|"
    r"iot|internet of things|connectable product|network equipment|network device|"
    r"router|switch|firewall|gateway|wireless ap|cryptographic module|crypto module|"
    r"认证|检测|测评|标签|标识|计划|方案|目录|清单|网络关键设备|网络安全专用产品|"
    r"专用网络安全产品|商用密码产品|密码产品|关键信息基础设施产品|联网产品|"
    r"物联网|智能设备|网络设备|路由器|交换机|网关|防火墙|安全产品"
    r")"
)


def classify_product_coverage(
    verified_record_count: int,
    product_verified_count: int,
    coverage_status: str,
    product_research_status: str | None = None,
) -> tuple[str, str]:
    if product_verified_count > 0:
        return (
            "product_regime_verified",
            "已找到产品级网络安全法规/认证/标准；继续补全文档、规格和更新监控",
        )
    if product_research_status == "no_product_regime_found_verified":
        return (
            "no_product_regime_found_verified",
            "已查官方监管/标准机构，未发现独立产品级网络安全制度；定期复核官方源",
        )
    if verified_record_count > 0:
        return (
            "general_cyber_law_verified",
            "已有通用网络安全官方证据；继续查找产品级认证/准入/标准，找不到则标记无产品制度",
        )
    if coverage_status == "researched_no_specific_source":
        return (
            "no_product_regime_found_verified",
            "已查官方监管/标准机构，未发现独立产品级网络安全制度；定期复核官方源",
        )
    return (
        "pending_source_research",
        "继续补官方证据链接；拿到官方链接即可先进入官方源确认状态",
    )


def refresh() -> dict[str, int]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO country_source_coverage (
                    country_code,
                    official_source_count,
                    source_record_count,
                    verified_record_count,
                    suspicious_record_count,
                    quarantined_record_count,
                    product_coverage_status,
                    product_verified_count,
                    general_verified_count,
                    review_note,
                    coverage_status,
                    next_action,
                    last_checked_at
                )
                SELECT
                    c.code,
                    COUNT(DISTINCT os.id) FILTER (WHERE os.enabled) AS official_source_count,
                    COUNT(DISTINCT sr.id) AS source_record_count,
                    COUNT(DISTINCT ci.id) FILTER (WHERE ci.authenticity_status='verified') AS verified_record_count,
                    COUNT(DISTINCT ci.id) FILTER (WHERE ci.authenticity_status='suspicious') AS suspicious_record_count,
                    COUNT(DISTINCT ci.id) FILTER (WHERE ci.authenticity_status='quarantined') AS quarantined_record_count,
                    CASE
                        WHEN COUNT(DISTINCT ci.id) FILTER (
                            WHERE ci.authenticity_status='verified'
                              AND ci.regime_category='product_regime'
                        ) > 0
                            THEN 'product_regime_verified'
                        WHEN COALESCE(MAX(cpro.outcome_status), '') = 'no_product_regime_found_verified'
                            THEN 'no_product_regime_found_verified'
                        WHEN COUNT(DISTINCT ci.id) FILTER (WHERE ci.authenticity_status='verified') > 0
                            THEN 'general_cyber_law_verified'
                        WHEN COALESCE(MAX(csc.coverage_status), '') = 'researched_no_specific_source'
                            THEN 'no_product_regime_found_verified'
                        ELSE 'pending_source_research'
                    END AS product_coverage_status,
                    COUNT(DISTINCT ci.id) FILTER (
                        WHERE ci.authenticity_status='verified'
                          AND ci.regime_category='product_regime'
                    ) AS product_verified_count,
                    COUNT(DISTINCT ci.id) FILTER (
                        WHERE ci.authenticity_status='verified'
                          AND ci.regime_category='general_cyber_law'
                    ) AS general_verified_count,
                    CASE
                        WHEN COUNT(DISTINCT ci.id) FILTER (
                            WHERE ci.authenticity_status='verified'
                              AND ci.regime_category='product_regime'
                        ) > 0
                            THEN 'product_regime_verified: 已有产品级网络安全法规/认证/标准官方证据'
                        WHEN COALESCE(MAX(cpro.outcome_status), '') = 'no_product_regime_found_verified'
                            THEN COALESCE(MAX(cpro.review_note), 'no_product_regime_found_verified: 已查官方监管/标准机构，未发现独立产品级网络安全制度')
                        WHEN COUNT(DISTINCT ci.id) FILTER (WHERE ci.authenticity_status='verified') > 0
                            THEN 'general_cyber_law_verified: 已有通用网络安全法规/政策/战略官方证据，仍需确认是否存在产品级认证/准入/标准'
                        WHEN COALESCE(MAX(csc.coverage_status), '') = 'researched_no_specific_source'
                            THEN 'no_product_regime_found_verified: 已查官方监管/标准机构，未发现独立产品级网络安全制度'
                        ELSE 'pending_source_research: 尚未形成官方证据闭环'
                    END AS review_note,
                    CASE
                        WHEN COUNT(DISTINCT ci.id) FILTER (WHERE ci.authenticity_status='verified') > 0
                            THEN 'verified_records_available'
                        WHEN COUNT(DISTINCT os.id) FILTER (WHERE os.enabled) > 0
                            THEN 'official_sources_seeded'
                        ELSE 'needs_source_research'
                    END AS coverage_status,
                    CASE
                        WHEN COALESCE(MAX(cpro.outcome_status), '') = 'no_product_regime_found_verified'
                            THEN '已查无独立产品级制度；定期复核官方源'
                        WHEN COUNT(DISTINCT ci.id) FILTER (WHERE ci.authenticity_status='verified') > 0
                            THEN '继续监控官方源并补全文档/规格'
                        WHEN COUNT(DISTINCT os.id) FILTER (WHERE os.enabled) > 0
                            THEN '运行官方源同步、下载工件并进入审核'
                        ELSE '亲自联网查找官方监管/标准/认证源'
                    END AS next_action,
                    NOW()
                FROM countries c
                LEFT JOIN country_source_coverage csc ON csc.country_code = c.code
                LEFT JOIN country_product_research_outcomes cpro ON cpro.country_code = c.code
                LEFT JOIN official_sources os ON os.country_code = c.code
                LEFT JOIN source_records sr ON sr.country_code = c.code
                LEFT JOIN compliance_index ci ON ci.country_code = c.code
                WHERE c.enabled = TRUE
                GROUP BY c.code
                ON CONFLICT (country_code)
                DO UPDATE SET
                    official_source_count=EXCLUDED.official_source_count,
                    source_record_count=EXCLUDED.source_record_count,
                    verified_record_count=EXCLUDED.verified_record_count,
                    suspicious_record_count=EXCLUDED.suspicious_record_count,
                    quarantined_record_count=EXCLUDED.quarantined_record_count,
                    product_coverage_status=EXCLUDED.product_coverage_status,
                    product_verified_count=EXCLUDED.product_verified_count,
                    general_verified_count=EXCLUDED.general_verified_count,
                    review_note=EXCLUDED.review_note,
                    coverage_status=CASE
                        WHEN country_source_coverage.coverage_status='researched_no_specific_source'
                             AND EXCLUDED.official_source_count = 0
                            THEN country_source_coverage.coverage_status
                        ELSE EXCLUDED.coverage_status
                    END,
                    next_action=EXCLUDED.next_action,
                    last_checked_at=NOW(),
                    updated_at=NOW()
                """,
            )

            cur.execute(
                """
                UPDATE country_source_coverage
                SET product_coverage_status='no_product_regime_found_verified',
                    product_verified_count=0,
                    general_verified_count=0,
                    review_note='no_product_regime_found_verified: 已查官方监管/标准机构，未发现独立产品级网络安全制度',
                    next_action='已查无独立产品级制度；定期复核官方源',
                    updated_at=NOW()
                WHERE coverage_status='researched_no_specific_source'
                  AND verified_record_count=0
                """
            )

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT coverage_status, COUNT(*) AS count
            FROM country_source_coverage
            GROUP BY coverage_status
            ORDER BY coverage_status
            """
        )
        summary = {row["coverage_status"]: int(row["count"]) for row in cur.fetchall()}
        cur.execute("SELECT COUNT(*) AS count FROM country_source_coverage")
        summary["total"] = int(cur.fetchone()["count"])
        return summary


if __name__ == "__main__":
    result = refresh()
    print("country_source_coverage refreshed")
    for key, value in result.items():
        print(f"{key}={value}")
