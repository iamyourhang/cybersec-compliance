#!/usr/bin/env python3
"""
Import a local artifact package on the server.

This script intentionally does not make authenticity decisions. It only
validates the package, stores the artifact through the existing document/COS
ingest service, and optionally parses PDF documents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.document.source_ingest import OfficialSourceIngestService
from database.repository import ComplianceRepository


PDF_SIGNATURE = b"%PDF"
HTML_MARKERS = (b"<html", b"<!doctype html", b"<body")
ERROR_PAGE_MARKERS = (
    "404",
    "page not found",
    "not found",
    "access denied",
    "forbidden",
    "cloudflare",
    "captcha",
    "login",
)


def _normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower().removeprefix("www.")


def _domain_allowed(url: str, allowed_domains: Iterable[str]) -> bool:
    parsed = urlparse(url)
    domain = _normalize_domain(parsed.netloc)
    if parsed.scheme not in {"http", "https"} or not domain:
        return False
    for allowed in allowed_domains:
        normalized = _normalize_domain(str(allowed))
        if domain == normalized or domain.endswith(f".{normalized}"):
            return True
    return False


def _allowed_domains(row: dict[str, Any]) -> list[str]:
    domains = row.get("allowed_domains") or []
    if isinstance(domains, str):
        domains = [part.strip() for part in domains.split(",") if part.strip()]
    official_url = (row.get("official_url") or "").strip()
    if official_url:
        host = _normalize_domain(urlparse(official_url).netloc)
        if host:
            domains = [*domains, host]
    return sorted({_normalize_domain(domain) for domain in domains if domain})


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _looks_like_error_page(body: bytes) -> bool:
    text = body[:4096].decode("utf-8", errors="ignore").lower()
    return any(marker in text for marker in ERROR_PAGE_MARKERS)


def _validate_content(path: Path, content: bytes, content_type: str) -> str:
    lower_type = (content_type or "").lower()
    lower_name = path.name.lower()
    lower_body = content[:500].lower()
    if "application/pdf" in lower_type or lower_name.endswith(".pdf") or content.startswith(PDF_SIGNATURE):
        return "pdf"
    if "html" in lower_type or lower_name.endswith((".html", ".htm")) or any(marker in lower_body for marker in HTML_MARKERS):
        if _looks_like_error_page(content):
            raise ValueError(f"疑似错误页/拦截页，不导入: {path}")
        return "html"
    raise ValueError(f"仅支持 PDF/HTML 工件: {path}")


def _maybe_parse_document(doc_id: str, file_type: str, parse_document: bool) -> None:
    if not parse_document or file_type not in {"pdf", "html"}:
        return
    from collector.document.index_service import DocumentIndexService
    from collector.document.parse_service import DocumentParseService

    parse_result = DocumentParseService().parse_document(doc_id, write_to_knowledge=False)
    if parse_result.get("success"):
        DocumentIndexService().index_document(doc_id)


def import_artifact_manifest(
    manifest_path: str | Path,
    artifact_dir: Optional[str | Path] = None,
    compliance_repo=ComplianceRepository,
    ingest_service: Optional[OfficialSourceIngestService] = None,
    requested_by: str = "local-artifact-bridge",
    parse_pdf: bool = True,
) -> list[dict[str, Any]]:
    manifest_path = Path(manifest_path)
    artifact_dir = Path(artifact_dir) if artifact_dir else manifest_path.parent
    results: list[dict[str, Any]] = []
    for row in _read_manifest(manifest_path):
        allowed_domains = _allowed_domains(row)
        official_url = (row.get("official_url") or "").strip()
        artifact_url = (row.get("artifact_url") or official_url).strip()
        if not official_url or not allowed_domains or not _domain_allowed(official_url, allowed_domains):
            raise ValueError(f"official_url 不在官方域名白名单内: {official_url}")
        if artifact_url and not _domain_allowed(artifact_url, allowed_domains):
            raise ValueError(f"artifact_url 不在官方域名白名单内: {artifact_url}")

        local_file = Path(str(row.get("local_file") or ""))
        if local_file.is_absolute() or ".." in local_file.parts:
            raise ValueError(f"local_file 非法: {local_file}")
        artifact_path = artifact_dir / local_file
        if not artifact_path.exists():
            raise ValueError(f"工件文件不存在: {artifact_path}")

        content = artifact_path.read_bytes()
        if not content:
            raise ValueError(f"工件文件为空: {artifact_path}")
        actual_sha = hashlib.sha256(content).hexdigest()
        expected_sha = str(row.get("sha256") or "")
        if actual_sha != expected_sha:
            raise ValueError(f"SHA256 不匹配: {artifact_path}")
        file_type = _validate_content(artifact_path, content, row.get("content_type") or "")

        compliance_id = str(row.get("compliance_id") or "").strip()
        if compliance_id:
            record = compliance_repo.get_by_id(compliance_id)
            if not record:
                raise ValueError(f"找不到 compliance 记录: {compliance_id}")
            record = dict(record)
        else:
            source_record_id = str(row.get("source_record_id") or "").strip()
            if not source_record_id:
                raise ValueError("manifest 必须包含 compliance_id 或 source_record_id")
            record = {
                "id": source_record_id,
                "source_status": "candidate",
                "source_record_id": source_record_id,
                "compliance_id": None,
                "country_code": row.get("country_code"),
                "title": row.get("title"),
                "official_url": official_url,
            }

        if row.get("source_record_id"):
            record["source_record_id"] = row.get("source_record_id")
        active_ingest_service = ingest_service or OfficialSourceIngestService()
        result = active_ingest_service.ingest_uploaded_source(
            record,
            official_url=official_url,
            file_name=artifact_path.name,
            content=content,
            content_type=row.get("content_type") or ("application/pdf" if file_type == "pdf" else "text/html"),
            artifact_url=artifact_url,
            requested_by=requested_by,
        )
        _maybe_parse_document(str(result["doc_id"]), file_type, parse_document=parse_pdf)
        results.append(
            {
                "status": "imported",
                "doc_id": result["doc_id"],
                "title": row.get("title") or artifact_path.name,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Import local official artifact package into COS/document store.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--artifact-dir", default=None)
    parser.add_argument("--requested-by", default="local-artifact-bridge")
    parser.add_argument("--no-parse", action="store_true", help="Import only; do not parse/index PDF or HTML documents.")
    args = parser.parse_args()

    results = import_artifact_manifest(
        manifest_path=args.manifest,
        artifact_dir=args.artifact_dir,
        requested_by=args.requested_by,
        parse_pdf=not args.no_parse,
    )
    print(json.dumps({"imported": len(results), "items": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
