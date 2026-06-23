#!/usr/bin/env python3
"""Import the sanitized public verified-only data pack.

Run this after `scripts/init_db.py --seed` when setting up a local copy.
The importer preserves public UUIDs, rebuilds review/canonical/index read
models, and intentionally leaves raw PDFs/COS objects out of the database.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import psycopg2.extras


BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.connection import close_pool, get_connection, get_cursor  # noqa: E402
from database.repository import ComplianceIndexRepository  # noqa: E402


DEFAULT_INPUT_DIR = BASE_DIR / "data" / "public"

JSONB_COLUMNS = {
    ("official_sources", "parser_config"),
    ("compliance_knowledge", "requirements"),
    ("compliance_knowledge", "authenticity_reasons"),
    ("content_translations", "source_text"),
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _adapt_value(table: str, column: str, value: Any) -> Any:
    if value is not None and (table, column) in JSONB_COLUMNS and isinstance(value, (dict, list)):
        return psycopg2.extras.Json(value)
    return value


def _upsert_rows(
    table: str,
    rows: list[dict[str, Any]],
    columns: list[str],
    conflict_columns: list[str],
    *,
    update_columns: Iterable[str] | None = None,
) -> int:
    if not rows:
        return 0
    update_columns = list(update_columns or [col for col in columns if col not in conflict_columns])
    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(columns)
    conflict_sql = ", ".join(conflict_columns)
    if update_columns:
        update_sql = ", ".join(f"{col}=EXCLUDED.{col}" for col in update_columns)
        conflict_action = f"DO UPDATE SET {update_sql}"
    else:
        conflict_action = "DO NOTHING"
    sql = f"""
        INSERT INTO {table} ({column_sql})
        VALUES ({placeholders})
        ON CONFLICT ({conflict_sql})
        {conflict_action}
    """
    values = [
        tuple(_adapt_value(table, col, row.get(col)) for col in columns)
        for row in rows
    ]
    with get_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, values, page_size=200)
    return len(rows)


def _rebuild_review_and_canonical(compliance_ids: list[str]) -> None:
    if not compliance_ids:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO review_cases (
                    compliance_id, current_status, risk_score, reasons,
                    evidence_note, source_download_status, checked_at, checked_by
                )
                SELECT id, authenticity_status,
                       COALESCE(authenticity_risk_score, 0),
                       COALESCE(authenticity_reasons, '[]'::jsonb),
                       authenticity_evidence,
                       source_download_status,
                       authenticity_checked_at,
                       COALESCE(authenticity_checked_by, 'public_data_import')
                FROM compliance_knowledge
                WHERE id = ANY(%s::uuid[])
                ON CONFLICT (compliance_id)
                DO UPDATE SET
                    current_status=EXCLUDED.current_status,
                    risk_score=EXCLUDED.risk_score,
                    reasons=EXCLUDED.reasons,
                    evidence_note=EXCLUDED.evidence_note,
                    source_download_status=EXCLUDED.source_download_status,
                    checked_at=EXCLUDED.checked_at,
                    checked_by=EXCLUDED.checked_by,
                    updated_at=NOW()
                """,
                (compliance_ids,),
            )
            cur.execute(
                """
                INSERT INTO canonical_requirements (
                    compliance_id, source_artifact_id, document_id, country_code,
                    name, entry_type, mandatory, issuing_body, official_url,
                    verification_status, requirement_payload
                )
                SELECT
                    ck.id,
                    sa.id,
                    ck.source_document_id,
                    ck.country_code,
                    ck.name,
                    ck.entry_type::TEXT,
                    ck.mandatory::TEXT,
                    ck.issuing_body,
                    ck.official_url,
                    ck.authenticity_status,
                    jsonb_strip_nulls(
                        jsonb_build_object(
                            'technical_standards', ck.technical_standards,
                            'regulation_basis', ck.regulation_basis,
                            'scope_description', ck.scope_description,
                            'requirements', ck.requirements,
                            'assessment_procedure', ck.assessment_procedure,
                            'remarks', ck.remarks
                        )
                    )
                FROM compliance_knowledge ck
                LEFT JOIN LATERAL (
                    SELECT id
                    FROM source_artifacts
                    WHERE compliance_id = ck.id
                    ORDER BY downloaded_at DESC NULLS LAST, created_at DESC
                    LIMIT 1
                ) sa ON TRUE
                WHERE ck.id = ANY(%s::uuid[])
                ON CONFLICT (compliance_id)
                DO UPDATE SET
                    source_artifact_id=EXCLUDED.source_artifact_id,
                    document_id=EXCLUDED.document_id,
                    country_code=EXCLUDED.country_code,
                    name=EXCLUDED.name,
                    entry_type=EXCLUDED.entry_type,
                    mandatory=EXCLUDED.mandatory,
                    issuing_body=EXCLUDED.issuing_body,
                    official_url=EXCLUDED.official_url,
                    verification_status=EXCLUDED.verification_status,
                    requirement_payload=EXCLUDED.requirement_payload,
                    updated_at=NOW()
                """,
                (compliance_ids,),
            )


def _refresh_index(compliance_ids: list[str]) -> int:
    refreshed = 0
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM compliance_knowledge WHERE id = ANY(%s::uuid[])",
            (compliance_ids,),
        )
        records = [dict(row) for row in cur.fetchall()]
    for record in records:
        ComplianceIndexRepository.refresh_for_compliance(record)
        refreshed += 1
    return refreshed


def import_public_data(input_dir: Path) -> dict[str, int]:
    countries = _read_jsonl(input_dir / "countries.jsonl")
    products = _read_jsonl(input_dir / "products.jsonl")
    official_sources = _read_jsonl(input_dir / "official_sources.jsonl")
    jurisdiction_inheritance = _read_jsonl(input_dir / "jurisdiction_inheritance.jsonl")
    compliance = _read_jsonl(input_dir / "compliance_verified.jsonl")
    documents = _read_jsonl(input_dir / "documents_metadata.jsonl")
    artifacts = _read_jsonl(input_dir / "source_artifacts_manifest.jsonl")
    specs = _read_jsonl(input_dir / "spec_requirements.jsonl")
    translations = _read_jsonl(input_dir / "content_translations.jsonl")

    source_document_by_compliance = {
        row["id"]: row.get("source_document_id")
        for row in compliance
        if row.get("source_document_id")
    }
    exported_compliance_ids = {row["id"] for row in compliance}
    exported_document_ids = {row["id"] for row in documents}
    for row in compliance:
        row["verified"] = True
        row["authenticity_status"] = "verified"
        row["data_source"] = "public_verified_seed"
        # Break the compliance <-> document FK cycle during initial insert.
        row["source_document_id"] = None
    for row in documents:
        if row.get("compliance_id") not in exported_compliance_ids:
            row["compliance_id"] = None
        row["cos_key"] = f"public-data/not-included/{row['id']}"
        row["cos_url"] = None
        row["spec_cos_url"] = None
        row["spec_cos_key"] = None
        row.setdefault("uploaded_by", "public_data_import")
        row.setdefault("progress", 0)
        row.setdefault("spec_progress", 0)
    for row in artifacts:
        row["source_record_id"] = None
        if row.get("compliance_id") not in exported_compliance_ids:
            row["compliance_id"] = None
        if row.get("document_id") not in exported_document_ids:
            row["document_id"] = None
    for row in specs:
        row["source_chunk_ids"] = []

    counts: dict[str, int] = {}
    counts["countries"] = _upsert_rows(
        "countries",
        countries,
        ["code", "name_zh", "name_en", "region", "priority", "enabled"],
        ["code"],
    )
    counts["products"] = _upsert_rows(
        "products",
        products,
        ["code", "name_zh", "name_en", "category", "description", "enabled"],
        ["code"],
    )
    counts["official_sources"] = _upsert_rows(
        "official_sources",
        official_sources,
        [
            "id", "country_code", "name", "base_url", "list_url", "source_type",
            "allowed_domains", "entry_type_scope", "poll_interval_hours",
            "priority", "enabled", "parser_config",
        ],
        ["country_code", "name"],
        update_columns=[
            "base_url", "list_url", "source_type", "allowed_domains",
            "entry_type_scope", "poll_interval_hours", "priority",
            "enabled", "parser_config",
        ],
    )
    counts["jurisdiction_inheritance"] = _upsert_rows(
        "jurisdiction_inheritance",
        jurisdiction_inheritance,
        [
            "parent_code", "child_code", "relation_type", "reason",
            "effective_from", "effective_to", "enabled",
        ],
        ["parent_code", "child_code", "relation_type"],
    )
    counts["compliance_verified"] = _upsert_rows(
        "compliance_knowledge",
        compliance,
        [
            "id", "name", "name_local", "entry_type", "mandatory", "status",
            "country_code", "region_scope", "issuing_body", "technical_standards",
            "regulation_basis", "effective_date", "transition_end_date",
            "validity_period", "published_date", "applicable_products",
            "scope_description", "requirements", "testing_bodies",
            "assessment_procedure", "official_url", "official_url_backup",
            "remarks", "data_source", "verified", "confidence_score", "version",
            "authenticity_status", "authenticity_risk_score",
            "authenticity_reasons", "authenticity_checked_at",
            "authenticity_checked_by", "authenticity_evidence",
            "source_document_id", "source_artifact_url", "source_artifact_type",
            "source_artifact_sha256", "source_download_status",
            "source_downloaded_at",
        ],
        ["id"],
    )
    counts["documents_metadata"] = _upsert_rows(
        "regulation_documents",
        documents,
        [
            "id", "compliance_id", "name", "country_code", "file_name",
            "cos_key", "cos_url", "file_size", "file_type", "parse_status",
            "parsed_at", "index_status", "indexed_at", "page_count",
            "chunk_count", "content_hash", "spec_requirement_count",
            "created_at", "spec_cos_url", "spec_cos_key", "uploaded_by",
            "progress", "spec_progress",
        ],
        ["id"],
    )
    document_updates = [
        (doc_id, compliance_id)
        for compliance_id, doc_id in source_document_by_compliance.items()
        if doc_id in exported_document_ids
    ]
    if document_updates:
        with get_connection() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    UPDATE compliance_knowledge
                    SET source_document_id = %s
                    WHERE id = %s
                    """,
                    document_updates,
                    page_size=200,
                )
    counts["source_artifacts"] = _upsert_rows(
        "source_artifacts",
        artifacts,
        [
            "id", "source_record_id", "compliance_id", "document_id",
            "official_url", "artifact_url", "artifact_type", "artifact_sha256",
            "download_status", "downloaded_at", "created_at",
        ],
        ["id"],
    )
    counts["spec_requirements"] = _upsert_rows(
        "regulation_spec_requirements",
        specs,
        [
            "id", "document_id", "compliance_id", "country_code",
            "regulation_name", "req_id", "module_zh", "module_en",
            "title_zh", "title_en", "description_zh", "description_en",
            "applicable_products", "mandatory", "priority", "regulation_clause",
            "verification_method_zh", "verification_method_en", "notes_zh",
            "notes_en", "source_pages", "source_chunk_ids", "created_at",
            "updated_at",
        ],
        ["id"],
    )
    counts["content_translations"] = _upsert_rows(
        "content_translations",
        translations,
        [
            "id", "entity_type", "entity_id", "field_name", "source_language",
            "target_language", "source_text_hash", "source_text",
            "translated_text", "translation_status", "translated_at",
        ],
        ["id"],
    )

    compliance_ids = [row["id"] for row in compliance]
    _rebuild_review_and_canonical(compliance_ids)
    counts["compliance_index_refreshed"] = _refresh_index(compliance_ids)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Import sanitized public verified-only data.")
    parser.add_argument("--dir", type=Path, default=DEFAULT_INPUT_DIR, help="Input data/public directory.")
    args = parser.parse_args()

    if not args.dir.exists():
        raise SystemExit(f"Public data directory does not exist: {args.dir}")
    try:
        counts = import_public_data(args.dir)
    finally:
        close_pool()

    print(f"Imported public data pack from {args.dir}")
    for key, count in counts.items():
        print(f"  {key}: {count}")


if __name__ == "__main__":
    main()
