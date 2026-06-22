"""
scripts/verify_authoritative_links.py
对权威官方链接且编号与 URL 明确一致的记录做保守式批量核验。

Legacy notice:
  默认只允许 dry-run。正式库写入请走后台 Reviews/manual-source/官方源任务。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.audit.official_batch_verify import build_official_verification
from database.connection import get_cursor
from database.repository import ComplianceRepository


def ensure_legacy_opt_in(legacy_unsafe: bool) -> None:
    if not legacy_unsafe:
        raise SystemExit(
            "❌ verify_authoritative_links.py 默认禁止批量写库。\n"
            "请使用后台 Reviews/manual-source 官方证据链路；如确需临时排障，必须显式传入 --legacy-unsafe。"
        )


def load_records(limit: int, country: str | None, entry_type: str | None) -> list[dict]:
    sql = """
        SELECT id, name, country_code, entry_type, official_url, verified,
               confidence_score, authenticity_status
        FROM compliance_knowledge
        WHERE status='active'
          AND verified=FALSE
          AND official_url IS NOT NULL
          AND COALESCE(authenticity_status, 'candidate') <> 'quarantined'
    """
    params: list = []
    if country:
        sql += " AND country_code=%s"
        params.append(country)
    if entry_type and entry_type != "all":
        sql += " AND entry_type=%s"
        params.append(entry_type)
    sql += " ORDER BY updated_at DESC LIMIT %s"
    params.append(limit)
    with get_cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--country")
    parser.add_argument("--type", default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--checked-by", default="authoritative_link_verifier")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--legacy-unsafe", action="store_true", help="显式确认运行旧批量写回脚本（不推荐）")
    args = parser.parse_args()

    if not args.dry_run:
        ensure_legacy_opt_in(args.legacy_unsafe)

    verified_items = []
    for record in load_records(args.limit, args.country, args.type):
        verdict = build_official_verification(record)
        if not verdict:
            continue
        if not args.dry_run:
            ComplianceRepository.set_authenticity_review(
                str(record["id"]),
                authenticity_status="verified",
                risk_score=0,
                reasons=["authoritative_link_match"],
                checked_by=args.checked_by,
                evidence=verdict["evidence"],
            )
            ComplianceRepository.update(
                str(record["id"]),
                {
                    "verified": True,
                },
                force=True,
            )
        verified_items.append(
            {
                "id": str(record["id"]),
                "country_code": record["country_code"],
                "entry_type": record["entry_type"],
                "name": record["name"],
                "official_url": record["official_url"],
                "evidence": verdict["evidence"],
            }
        )

    if args.json:
        print(json.dumps(verified_items, ensure_ascii=False, indent=2))
        return

    print(f"verified_count={len(verified_items)}")
    for item in verified_items[:50]:
        print(f"{item['country_code']}\t{item['entry_type']}\t{item['id']}\t{item['name']}\t{item['evidence']}")


if __name__ == "__main__":
    main()
