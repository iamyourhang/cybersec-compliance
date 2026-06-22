"""
scripts/authenticity_audit.py
真实性审计脚本：基于规则评分，可选探测 official_url。

Legacy notice:
  默认可审计输出；写回数据库属于旧链路能力，必须显式传入 --legacy-unsafe。

用法:
  ./.venv/bin/python scripts/authenticity_audit.py --limit 50
  ./.venv/bin/python scripts/authenticity_audit.py --type certification --probe-urls --min-risk 60
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.audit.authenticity import assess_record_authenticity, probe_official_url
from collector.audit.official_batch_verify import build_official_verification
from database.connection import get_cursor
from database.repository import ComplianceRepository


def ensure_legacy_opt_in(legacy_unsafe: bool) -> None:
    if not legacy_unsafe:
        raise SystemExit(
            "❌ authenticity_audit.py 的 --persist 写回默认禁止。\n"
            "请使用后台 Reviews/manual-source 官方证据链路；如确需临时排障，必须显式传入 --legacy-unsafe。"
        )


def load_records(country: str | None, entry_type: str | None, limit: int, candidate_only: bool = False) -> list[dict]:
    sql = """
        SELECT ck.id, ck.name, ck.country_code, ck.entry_type, ck.issuing_body,
               ck.official_url, ck.verified, ck.confidence_score, ck.data_source, ck.status,
               ck.source_download_status, ck.source_download_error
        FROM compliance_knowledge ck
        WHERE ck.status = 'active'
    """
    params: list = []
    if candidate_only:
        sql += " AND COALESCE(ck.authenticity_status, 'candidate') = 'candidate'"
    if country:
        sql += " AND ck.country_code = %s"
        params.append(country)
    if entry_type and entry_type != "all":
        sql += " AND ck.entry_type = %s"
        params.append(entry_type)
    sql += " ORDER BY ck.updated_at DESC LIMIT %s"
    params.append(limit)
    with get_cursor() as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def determine_final_review(record: dict, probe: dict | None = None) -> dict:
    if record.get("verified"):
        return {
            "authenticity_status": "verified",
            "risk_score": 0,
            "reasons": ["verified_flag_present"],
            "evidence": "记录已存在 verified 标记，收口同步 authenticity_status",
        }

    verified = build_official_verification(record)
    if verified:
        return {
            "authenticity_status": "verified",
            "risk_score": 0,
            "reasons": ["authoritative_link_match"],
            "evidence": verified["evidence"],
        }

    verdict = assess_record_authenticity(record, probe=probe)
    status = "quarantined" if verdict["recommended_action"] == "quarantine" else "suspicious"
    return {
        "authenticity_status": status,
        "risk_score": verdict["risk_score"],
        "reasons": verdict["reasons"],
        "evidence": ", ".join(verdict["reasons"]),
        "verdict": verdict,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", help="只审计指定国家")
    parser.add_argument("--type", default="all", help="regulation/standard/certification/all")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--min-risk", type=int, default=60)
    parser.add_argument("--probe-urls", action="store_true", help="联网探测 official_url")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--persist", action="store_true", help="将审计结果写回数据库")
    parser.add_argument("--quarantine-critical", action="store_true", help="persist 时将 critical 标记为 quarantined")
    parser.add_argument("--finalize", action="store_true", help="将未完成条目直接收口到 verified/suspicious/quarantined，不保留 candidate")
    parser.add_argument("--candidate-only", action="store_true", help="只处理 authenticity_status=candidate 的条目")
    parser.add_argument("--checked-by", default="authenticity_audit_script", help="写回数据库时记录执行者")
    parser.add_argument("--legacy-unsafe", action="store_true", help="显式确认运行旧审计写回脚本（不推荐）")
    args = parser.parse_args()

    if args.persist:
        ensure_legacy_opt_in(args.legacy_unsafe)

    records = load_records(args.country, args.type, args.limit, candidate_only=args.candidate_only)
    items = []
    for record in records:
        probe = probe_official_url(record["official_url"]) if args.probe_urls and record.get("official_url") else None
        verdict = assess_record_authenticity(record, probe=probe)
        final_review = determine_final_review(record, probe=probe) if args.finalize else None
        if args.persist:
            if args.finalize:
                authenticity_status = final_review["authenticity_status"]
                evidence = final_review["evidence"]
                reasons = final_review["reasons"]
                risk_score = final_review["risk_score"]
            else:
                evidence = ", ".join(verdict["reasons"])
                authenticity_status = "verified" if record.get("verified") else "candidate"
                if verdict["risk_level"] in {"medium", "high"}:
                    authenticity_status = "suspicious"
                if args.quarantine_critical and verdict["risk_level"] == "critical":
                    authenticity_status = "quarantined"
                reasons = verdict["reasons"]
                risk_score = verdict["risk_score"]
            ComplianceRepository.set_authenticity_review(
                str(record["id"]),
                authenticity_status=authenticity_status,
                risk_score=risk_score,
                reasons=reasons,
                checked_by=args.checked_by,
                evidence=evidence,
            )
            if args.finalize:
                update_data = {"verified": authenticity_status == "verified"}
                if authenticity_status != "verified" and record.get("source_download_status") == "pending":
                    if record.get("official_url"):
                        update_data["source_download_status"] = "failed"
                        if probe and probe.get("error"):
                            update_data["source_download_error"] = str(probe.get("error"))[:1000]
                        elif probe and probe.get("status_code"):
                            update_data["source_download_error"] = f"official_url probe returned status {probe.get('status_code')}"
                    else:
                        update_data["source_download_status"] = "failed"
                        update_data["source_download_error"] = "No official URL available for final verification"
                ComplianceRepository.update(str(record["id"]), update_data, force=True)
        if verdict["risk_score"] < args.min_risk:
            continue
        items.append(
            {
                **record,
                **verdict,
                "probe": probe,
            }
        )

    items.sort(key=lambda item: item["risk_score"], reverse=True)

    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2, default=str))
        return

    print(f"命中高风险条目: {len(items)}")
    for item in items:
        print(
            f"[{item['risk_level'].upper()} {item['risk_score']:>3}] "
            f"{item['country_code']} | {item['entry_type']} | {item['name']}"
        )
        print(f"  reasons: {', '.join(item['reasons'])}")
        if item.get("official_url"):
            print(f"  official_url: {item['official_url']}")
        if item.get("probe"):
            probe = item["probe"]
            print(
                f"  probe: status={probe.get('status_code')} "
                f"final_url={probe.get('final_url')} error={probe.get('error')}"
            )


if __name__ == "__main__":
    main()
