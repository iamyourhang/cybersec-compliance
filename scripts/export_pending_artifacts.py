#!/usr/bin/env python3
"""
Export records that need local artifact fetching.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.official_sources.repository import OfficialSourceRepository
from collector.official_sources.relevance import is_cybersecurity_relevant
from database.connection import get_cursor
from database.repository import SourceRecordRepository


def _normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower().removeprefix("www.")


def _domains_from_url(url: Optional[str]) -> list[str]:
    if not url:
        return []
    domain = _normalize_domain(urlparse(url).netloc)
    return [domain] if domain else []


def _source_name_from_data_source(data_source: Optional[str]) -> Optional[str]:
    marker = "official_source:"
    if not data_source or marker not in data_source:
        return None
    return data_source.split(marker, 1)[-1].strip() or None


def _allowed_domains(
    row: dict[str, Any],
    official_sources: Iterable[dict[str, Any]],
    source_name: Optional[str] = None,
) -> list[str]:
    country_code = row.get("country_code")
    matched: list[str] = []
    fallback: list[str] = []
    for source in official_sources:
        if source.get("country_code") != country_code:
            continue
        domains = source.get("allowed_domains") or []
        fallback.extend(domains)
        if source_name and source.get("name") == source_name:
            matched.extend(domains)
    domains = matched or fallback
    domains.extend(_domains_from_url(row.get("official_url") or row.get("source_url")))
    return sorted({_normalize_domain(domain) for domain in domains if domain})


def build_export_rows(
    compliance_records: list[dict[str, Any]],
    source_records: list[dict[str, Any]],
    official_sources: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for record in compliance_records:
        official_url = (record.get("official_url") or "").strip()
        if not official_url:
            continue
        if not is_cybersecurity_relevant(f"{record.get('name') or ''} {official_url} {record.get('scope_description') or ''}"):
            continue
        key = ("compliance", str(record.get("id")))
        if key in seen:
            continue
        seen.add(key)
        source_name = _source_name_from_data_source(record.get("data_source"))
        rows.append(
            {
                "source_kind": "compliance",
                "source_record_id": "",
                "compliance_id": str(record.get("id") or ""),
                "country_code": record.get("country_code"),
                "title": record.get("name"),
                "entry_type": record.get("entry_type"),
                "official_url": official_url,
                "artifact_url": record.get("source_artifact_url") or official_url,
                "allowed_domains": _allowed_domains(record, official_sources, source_name=source_name),
                "source_download_status": record.get("source_download_status") or "pending",
                "source_download_error": record.get("source_download_error") or "",
                "evidence_note": f"待本地联网补源：{record.get('name') or official_url}",
            }
        )

    for record in source_records:
        target_url = (record.get("artifact_url") or record.get("source_url") or "").strip()
        if not target_url:
            continue
        if not is_cybersecurity_relevant(f"{record.get('title') or ''} {target_url} {record.get('summary') or ''}"):
            continue
        key = ("source_record", str(record.get("id")))
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source_kind": "source_record",
                "source_record_id": str(record.get("id") or ""),
                "compliance_id": str(record.get("compliance_id") or ""),
                "country_code": record.get("country_code"),
                "title": record.get("title"),
                "entry_type": record.get("entry_type"),
                "official_url": record.get("source_url") or target_url,
                "artifact_url": target_url,
                "allowed_domains": _allowed_domains(record, official_sources),
                "source_download_status": record.get("download_status") or "pending",
                "source_download_error": record.get("download_error") or "",
                "evidence_note": f"待本地联网补源：{record.get('title') or target_url}",
            }
        )

    status_rank = {"failed": 0, "pending": 1, None: 2}
    rows.sort(key=lambda row: (status_rank.get(row.get("source_download_status"), 2), row.get("country_code") or "", row.get("title") or ""))
    return rows[:limit]


def _load_compliance_records(limit: int) -> list[dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT ck.*
            FROM compliance_knowledge ck
            LEFT JOIN source_artifacts sa
              ON sa.compliance_id = ck.id
            WHERE COALESCE(ck.authenticity_status, 'candidate') <> 'quarantined'
              AND ck.official_url IS NOT NULL
              AND (
                    ck.source_download_status IN ('pending', 'failed')
                    OR sa.id IS NULL
                    OR sa.download_status IN ('pending', 'failed')
              )
            ORDER BY
              CASE WHEN ck.source_download_status='failed' THEN 0 ELSE 1 END,
              ck.updated_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def export_pending_artifacts(output_path: str | Path, limit: int = 200) -> list[dict[str, Any]]:
    official_sources = OfficialSourceRepository().list_all(enabled_only=False)
    compliance_records = _load_compliance_records(limit)
    source_records = SourceRecordRepository.list_pending_artifact_records(limit=limit)
    rows = build_export_rows(
        compliance_records=compliance_records,
        source_records=source_records,
        official_sources=official_sources,
        limit=limit,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Export official-source records that need local artifact fetching.")
    parser.add_argument("--out", default="pending_artifacts.jsonl")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    rows = export_pending_artifacts(args.out, limit=args.limit)
    print(json.dumps({"exported": len(rows), "output": str(args.out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
