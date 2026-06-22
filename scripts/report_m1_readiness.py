#!/usr/bin/env python3
"""M1 readiness report for verified public knowledge-base usage.

The report is intentionally read-only. It checks whether the user-facing Screen
and Agent have enough verified data, source links, ready documents, chunks, and
spec requirements for the priority markets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.connection import get_cursor


DEFAULT_MARKETS = (
    "EU",
    "US",
    "GB",
    "CN",
    "JP",
    "KR",
    "SG",
    "AU",
    "CA",
    "IN",
    "BR",
    "TW",
    "FR",
    "DE",
)


def _split_codes(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_MARKETS)
    return [code.strip().upper() for code in value.split(",") if code.strip()]


def build_report(markets: Iterable[str]) -> dict:
    codes = list(dict.fromkeys(code.upper() for code in markets))
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) AS verified_records,
                COUNT(*) FILTER (WHERE regime_category='product_regime') AS product_records,
                COUNT(DISTINCT country_code) AS verified_jurisdictions
            FROM compliance_index
            WHERE status='active'
              AND authenticity_status='verified'
            """
        )
        global_summary = dict(cur.fetchone())

        cur.execute(
            """
            SELECT
                COUNT(*) AS spec_requirements,
                COUNT(DISTINCT document_id) AS spec_documents
            FROM regulation_spec_requirements
            """
        )
        spec_summary = dict(cur.fetchone())

        cur.execute(
            """
            SELECT
                c.code,
                c.name_zh,
                c.priority,
                COALESCE(csc.coverage_status, 'needs_source_research') AS coverage_status,
                COALESCE(csc.product_coverage_status, 'pending_source_research') AS product_coverage_status,
                COALESCE(csc.verified_record_count, 0) AS verified_record_count,
                COALESCE(csc.product_verified_count, 0) AS product_verified_count,
                COALESCE(csc.official_source_count, 0) AS official_source_count,
                COALESCE(doc.ready_docs, 0) AS ready_docs,
                COALESCE(doc.chunks, 0) AS chunks,
                COALESCE(spec.spec_count, 0) AS spec_count
            FROM countries c
            LEFT JOIN country_source_coverage csc ON csc.country_code = c.code
            LEFT JOIN (
                SELECT
                    ci.country_code,
                    COUNT(*) FILTER (WHERE d.index_status='ready' AND COALESCE(d.chunk_count,0)>0) AS ready_docs,
                    COALESCE(SUM(d.chunk_count), 0) AS chunks
                FROM compliance_index ci
                LEFT JOIN regulation_documents d ON d.compliance_id=ci.compliance_id
                WHERE ci.status='active'
                  AND ci.authenticity_status='verified'
                GROUP BY ci.country_code
            ) doc ON doc.country_code=c.code
            LEFT JOIN (
                SELECT country_code, COUNT(*) AS spec_count
                FROM regulation_spec_requirements
                GROUP BY country_code
            ) spec ON spec.country_code=c.code
            WHERE c.code = ANY(%s)
            ORDER BY array_position(%s::text[], c.code)
            """,
            (codes, codes),
        )
        markets_summary = [dict(row) for row in cur.fetchall()]

    gaps = []
    for row in markets_summary:
        reasons = []
        if row["coverage_status"] != "verified_records_available":
            reasons.append("no_verified_record")
        if row["product_coverage_status"] != "product_regime_verified":
            reasons.append("no_product_regime")
        if row["ready_docs"] <= 0:
            reasons.append("no_ready_document")
        if row["spec_count"] <= 0:
            reasons.append("no_spec_requirements")
        if reasons:
            gaps.append({"code": row["code"], "name_zh": row["name_zh"], "reasons": reasons})

    return {
        "global": {**global_summary, **spec_summary},
        "markets": markets_summary,
        "gaps": gaps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report M1 readiness for priority cybersecurity compliance markets.")
    parser.add_argument("--markets", help="Comma-separated market codes. Defaults to M1 priority set.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a compact table.")
    args = parser.parse_args()

    report = build_report(_split_codes(args.markets))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, default=str, indent=2))
        return

    print("M1 readiness")
    print(json.dumps(report["global"], ensure_ascii=False, default=str))
    for row in report["markets"]:
        print(
            f"{row['code']}\t{row['name_zh']}\tverified={row['verified_record_count']}\t"
            f"product={row['product_verified_count']}\tsources={row['official_source_count']}\t"
            f"ready_docs={row['ready_docs']}\tchunks={row['chunks']}\tspecs={row['spec_count']}\t"
            f"{row['coverage_status']}/{row['product_coverage_status']}"
        )
    if report["gaps"]:
        print("gaps:")
        for gap in report["gaps"]:
            print(f"- {gap['code']} {gap['name_zh']}: {', '.join(gap['reasons'])}")


if __name__ == "__main__":
    main()
