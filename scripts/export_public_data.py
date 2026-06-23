#!/usr/bin/env python3
"""Export a sanitized public verified-only data pack.

This script is intended to run on the production server. It exports the
valuable, public-facing compliance corpus without secrets, users, logs,
LLM channels, COS keys/URLs, raw PDFs, chunks, or embeddings.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID


BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.connection import close_pool, get_cursor  # noqa: E402


DEFAULT_OUTPUT_DIR = BASE_DIR / "data" / "public"
VERIFIED_STATUS = "verified"


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _as_dict(row: Any) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in dict(row).items()}


def _fetch_all(sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(sql, tuple(params or ()))
        return [_as_dict(row) for row in cur.fetchall()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def _load_verified_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row["id"]) for row in rows}


def _write_manifest(output_dir: Path, files: dict[str, int]) -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "policy": {
            "scope": "verified-only public cybersecurity compliance records",
            "excluded": [
                "candidate/suspicious/quarantined records",
                "users and authentication data",
                "LLM/API/COS/Feishu credentials",
                "runtime logs, scheduler history, and agent cases",
                "raw PDFs/HTML files, COS object keys/URLs, chunks, and embeddings",
            ],
            "note": "Documents are exported as metadata only. Re-download source files from official_url/artifact_url before re-indexing.",
        },
        "files": files,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def export_public_data(output_dir: Path) -> dict[str, int]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    countries = _fetch_all(
        """
        SELECT code, name_zh, name_en, region, priority::TEXT AS priority, enabled
        FROM countries
        ORDER BY code
        """
    )
    products = _fetch_all(
        """
        SELECT code, name_zh, name_en, category::TEXT AS category, description, enabled
        FROM products
        ORDER BY code
        """
    )
    official_sources = _fetch_all(
        """
        SELECT id, country_code, name, base_url, list_url, source_type,
               allowed_domains, entry_type_scope, poll_interval_hours,
               priority, enabled, parser_config
        FROM official_sources
        ORDER BY country_code, priority, name
        """
    )
    jurisdiction_inheritance = _fetch_all(
        """
        SELECT parent_code, child_code, relation_type, reason,
               effective_from, effective_to, enabled
        FROM jurisdiction_inheritance
        ORDER BY parent_code, child_code, relation_type
        """
    )
    compliance_verified = _fetch_all(
        """
        SELECT id, name, name_local, entry_type::TEXT AS entry_type,
               mandatory::TEXT AS mandatory, status::TEXT AS status,
               country_code, region_scope, issuing_body, technical_standards,
               regulation_basis, effective_date, transition_end_date,
               validity_period, published_date, applicable_products,
               scope_description, requirements, testing_bodies,
               assessment_procedure, official_url, official_url_backup,
               remarks, confidence_score, version,
               authenticity_status, authenticity_risk_score,
               authenticity_reasons, authenticity_checked_at,
               authenticity_checked_by, authenticity_evidence,
               source_document_id, source_artifact_url, source_artifact_type,
               source_artifact_sha256, source_download_status,
               source_downloaded_at
        FROM compliance_knowledge
        WHERE verified IS TRUE
          AND authenticity_status = %s
          AND official_url IS NOT NULL
          AND authenticity_evidence IS NOT NULL
          AND (
              source_artifact_sha256 IS NOT NULL
              OR source_document_id IS NOT NULL
              OR source_artifact_url IS NOT NULL
          )
        ORDER BY country_code, entry_type, name
        """,
        (VERIFIED_STATUS,),
    )
    verified_ids = _load_verified_ids(compliance_verified)

    documents_metadata = _fetch_all(
        """
        WITH verified AS (
            SELECT id, source_document_id
            FROM compliance_knowledge
            WHERE verified IS TRUE
              AND authenticity_status = %s
        ),
        public_document_ids AS (
            SELECT source_document_id AS id
            FROM verified
            WHERE source_document_id IS NOT NULL
            UNION
            SELECT rd.id
            FROM regulation_documents rd
            JOIN verified v ON v.id = rd.compliance_id
            UNION
            SELECT sa.document_id AS id
            FROM source_artifacts sa
            JOIN verified v ON v.id = sa.compliance_id
            WHERE sa.document_id IS NOT NULL
            UNION
            SELECT rs.document_id AS id
            FROM regulation_spec_requirements rs
            JOIN verified v ON v.id = rs.compliance_id
            WHERE rs.document_id IS NOT NULL
        )
        SELECT DISTINCT ON (rd.id)
               rd.id, rd.compliance_id, rd.name, rd.country_code,
               rd.file_name, rd.file_size, rd.file_type, rd.parse_status,
               rd.parsed_at, rd.index_status, rd.indexed_at, rd.page_count,
               rd.chunk_count, rd.content_hash, rd.spec_requirement_count,
               rd.created_at
        FROM regulation_documents rd
        JOIN public_document_ids pdi ON pdi.id = rd.id
        ORDER BY rd.id, rd.created_at DESC
        """,
        (VERIFIED_STATUS,),
    )
    document_ids = {str(row["id"]) for row in documents_metadata}

    source_artifacts = _fetch_all(
        """
        SELECT DISTINCT ON (sa.id)
               sa.id, sa.compliance_id, sa.document_id, sa.official_url,
               sa.artifact_url, sa.artifact_type, sa.artifact_sha256,
               sa.download_status, sa.downloaded_at, sa.created_at
        FROM source_artifacts sa
        JOIN compliance_knowledge ck
          ON ck.id = sa.compliance_id
        WHERE ck.verified IS TRUE
          AND ck.authenticity_status = %s
          AND (sa.official_url IS NOT NULL OR sa.artifact_url IS NOT NULL)
        ORDER BY sa.id, sa.created_at DESC
        """,
        (VERIFIED_STATUS,),
    )

    spec_requirements = _fetch_all(
        """
        SELECT DISTINCT ON (rs.id)
               rs.id, rs.document_id, rs.compliance_id, rs.country_code,
               rs.regulation_name, rs.req_id, rs.module_zh, rs.module_en,
               rs.title_zh, rs.title_en, rs.description_zh,
               rs.description_en, rs.applicable_products, rs.mandatory,
               rs.priority, rs.regulation_clause,
               rs.verification_method_zh, rs.verification_method_en,
               rs.notes_zh, rs.notes_en, rs.source_pages,
               rs.created_at, rs.updated_at
        FROM regulation_spec_requirements rs
        JOIN compliance_knowledge ck
          ON ck.id = rs.compliance_id
        WHERE ck.verified IS TRUE
          AND ck.authenticity_status = %s
        ORDER BY rs.id, rs.updated_at DESC
        """,
        (VERIFIED_STATUS,),
    )
    spec_ids = {str(row["id"]) for row in spec_requirements}

    translations: list[dict[str, Any]] = []
    if verified_ids or document_ids or spec_ids:
        translations = _fetch_all(
            """
            SELECT id, entity_type, entity_id, field_name, source_language,
                   target_language, source_text_hash, source_text,
                   translated_text, translation_status, translated_at
            FROM content_translations
            WHERE
                (entity_type = 'compliance_knowledge' AND entity_id = ANY(%s))
                OR (entity_type = 'regulation_documents' AND entity_id = ANY(%s))
                OR (entity_type = 'regulation_spec_requirements' AND entity_id = ANY(%s))
            ORDER BY entity_type, entity_id, field_name
            """,
            (list(verified_ids), list(document_ids), list(spec_ids)),
        )

    files = {
        "countries.jsonl": len(countries),
        "products.jsonl": len(products),
        "official_sources.jsonl": len(official_sources),
        "jurisdiction_inheritance.jsonl": len(jurisdiction_inheritance),
        "compliance_verified.jsonl": len(compliance_verified),
        "documents_metadata.jsonl": len(documents_metadata),
        "source_artifacts_manifest.jsonl": len(source_artifacts),
        "spec_requirements.jsonl": len(spec_requirements),
        "content_translations.jsonl": len(translations),
    }

    payloads = {
        "countries.jsonl": countries,
        "products.jsonl": products,
        "official_sources.jsonl": official_sources,
        "jurisdiction_inheritance.jsonl": jurisdiction_inheritance,
        "compliance_verified.jsonl": compliance_verified,
        "documents_metadata.jsonl": documents_metadata,
        "source_artifacts_manifest.jsonl": source_artifacts,
        "spec_requirements.jsonl": spec_requirements,
        "content_translations.jsonl": translations,
    }
    for filename, rows in payloads.items():
        _write_jsonl(output_dir / filename, rows)
    _write_manifest(output_dir, files)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Export sanitized public verified-only data.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    args = parser.parse_args()

    try:
        files = export_public_data(args.output)
    finally:
        close_pool()

    print(f"Exported public data pack to {args.output}")
    for filename, count in files.items():
        print(f"  {filename}: {count}")


if __name__ == "__main__":
    main()
