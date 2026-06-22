#!/usr/bin/env python3
"""Record countries researched with no specific cybersecurity/product compliance source found.

This script does not create verified compliance records. It only closes country coverage
items that were manually researched and currently have no official cybersecurity,
cybercrime, product-security, certification, or cybersecurity-standard source suitable
for the knowledge-base ingestion pipeline.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.connection import get_connection


RESEARCHED_NO_SPECIFIC_SOURCE: list[dict[str, Any]] = [
    {
        "country_code": "KP",
        "review_note": "2026-05-09: 查找朝鲜官方政府/监管/标准机构公开源，未定位到可追溯的网络安全法规、产品网络安全认证或官方正文/PDF源。",
    },
    {
        "country_code": "FM",
        "review_note": "2026-05-09: 查找密克罗尼西亚官方 ICT/法律公开源，未定位到独立网络安全法规或产品级网络安全认证源。",
    },
    {
        "country_code": "MH",
        "review_note": "2026-05-09: 查找马绍尔群岛官方政府/议会/通信源，未定位到独立网络安全法规或产品级网络安全认证源。",
    },
    {
        "country_code": "NR",
        "review_note": "2026-05-09: 查找瑙鲁官方司法/法律公开源，未定位到独立网络安全法规或产品级网络安全认证源。",
    },
    {
        "country_code": "PW",
        "review_note": "2026-05-09: 查找帕劳官方法律/司法/监管源，未定位到独立网络安全法规或产品级网络安全认证源。",
    },
    {
        "country_code": "VA",
        "review_note": "2026-05-09: 查找圣座官方公开源，未发现面向市场产品的网络安全法规、认证或国家网络安全合规制度。",
    },
    {
        "country_code": "DM",
        "review_note": "2026-05-09: 查找多米尼克官方法律源；仅定位到电子证据/电子交易等数字法律，未定位到生效的独立网络安全/网络犯罪法规或产品网络安全认证源。",
    },
    {
        "country_code": "HT",
        "review_note": "2026-05-09: 查找海地官方司法/政府公开源，未定位到可追溯的网络安全法规、认证或产品安全合规源。",
    },
    {
        "country_code": "SR",
        "review_note": "2026-05-09: 查找苏里南官方司法/检察/政府源，未定位到独立网络安全法规或产品级网络安全认证源。",
    },
    {
        "country_code": "CF",
        "review_note": "2026-05-09: 查找中非共和国官方法律/政府源，未定位到独立网络安全法规、国家 CERT 或产品级网络安全认证源。",
    },
    {
        "country_code": "ER",
        "review_note": "2026-05-09: 查找厄立特里亚官方政府/法律公开源，未定位到独立网络安全法规、国家 CERT 或产品级网络安全认证源。",
    },
    {
        "country_code": "GQ",
        "review_note": "2026-05-09: 查找赤道几内亚官方政府/法律公开源，未定位到独立网络安全法规、国家 CERT 或产品级网络安全认证源。",
    },
    {
        "country_code": "GW",
        "review_note": "2026-05-09: 查找几内亚比绍官方法律/执法/ICT源；仅发现国际网络犯罪公约签署旁证，未定位到本国独立网络安全法规或产品认证源。",
    },
    {
        "country_code": "KM",
        "review_note": "2026-05-09: 查找科摩罗官方司法/法律公开源，未定位到独立网络安全法规、国家 CERT 或产品级网络安全认证源。",
    },
]


def seed() -> int:
    updated = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for outcome in RESEARCHED_NO_SPECIFIC_SOURCE:
                cur.execute("SELECT 1 FROM countries WHERE code=%s", (outcome["country_code"],))
                if cur.fetchone() is None:
                    continue
                cur.execute(
                    """
                    INSERT INTO country_source_coverage (
                        country_code,
                        coverage_status,
                        product_coverage_status,
                        review_note,
                        next_action,
                        last_checked_at
                    )
                    VALUES (
                        %(country_code)s,
                        'researched_no_specific_source',
                        'no_product_regime_found_verified',
                        %(review_note)s,
                        '已查无独立产品级制度；定期复核官方源',
                        NOW()
                    )
                    ON CONFLICT (country_code) DO UPDATE SET
                        coverage_status='researched_no_specific_source',
                        product_coverage_status='no_product_regime_found_verified',
                        review_note=EXCLUDED.review_note,
                        next_action=EXCLUDED.next_action,
                        last_checked_at=NOW(),
                        updated_at=NOW()
                    WHERE country_source_coverage.verified_record_count = 0
                      AND country_source_coverage.official_source_count = 0
                    RETURNING 1
                    """,
                    outcome,
                )
                if cur.fetchone():
                    updated += 1
    return updated


if __name__ == "__main__":
    updated_count = seed()
    print(f"country research outcomes seeded: updated={updated_count}")
