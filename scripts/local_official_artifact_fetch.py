#!/usr/bin/env python3
"""
Local official artifact fetcher.

Run this on a workstation that can reach official websites when the server
network cannot. The output package is intentionally dumb: files plus a JSONL
manifest. The server re-validates everything before storing it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
import ssl


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


def _allowed_domains_for_item(item: dict[str, Any]) -> list[str]:
    domains = item.get("allowed_domains") or []
    if isinstance(domains, str):
        domains = [part.strip() for part in domains.split(",") if part.strip()]
    official_url = (item.get("official_url") or "").strip()
    if official_url:
        host = _normalize_domain(urlparse(official_url).netloc)
        if host:
            domains = [*domains, host]
    return sorted({_normalize_domain(domain) for domain in domains if domain})


def _read_input(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _default_opener_factory():
    context = ssl._create_unverified_context()
    return build_opener(HTTPRedirectHandler, HTTPSHandler(context=context))


def _content_type(headers: Any) -> str:
    if hasattr(headers, "get"):
        return headers.get("Content-Type", "") or ""
    return ""


def _is_pdf(url: str, content_type: str, body: bytes) -> bool:
    lowered_type = (content_type or "").lower()
    return "application/pdf" in lowered_type or url.lower().endswith(".pdf") or body.startswith(PDF_SIGNATURE)


def _is_html(content_type: str, body: bytes) -> bool:
    lowered_type = (content_type or "").lower()
    lowered_body = body[:500].lower()
    return "html" in lowered_type or any(marker in lowered_body for marker in HTML_MARKERS)


def _looks_like_error_page(body: bytes) -> bool:
    text = body[:4096].decode("utf-8", errors="ignore").lower()
    return any(marker in text for marker in ERROR_PAGE_MARKERS)


def _safe_file_name(title: str, source_url: str, sha256: str, file_type: str) -> str:
    source_name = PurePosixPath(urlparse(source_url).path).name
    stem = source_name.rsplit(".", 1)[0] if source_name else title
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")[:80] or "official_source"
    suffix = ".pdf" if file_type == "pdf" else ".html"
    return f"{sha256[:12]}_{stem}{suffix}"


def fetch_artifacts(
    input_path: str | Path,
    output_dir: str | Path,
    opener_factory: Optional[Callable[[], object]] = None,
    date_tag: Optional[str] = None,
    limit: Optional[int] = None,
    timeout: int = 20,
    continue_on_error: bool = False,
) -> list[dict[str, Any]]:
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    date_tag = date_tag or datetime.now(timezone.utc).strftime("%Y%m%d")
    package_dir = output_dir / date_tag
    package_dir.mkdir(parents=True, exist_ok=True)
    opener_factory = opener_factory or _default_opener_factory

    rows = _read_input(input_path)
    if limit is not None:
        rows = rows[:limit]

    manifest_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    for item in rows:
        try:
            allowed_domains = _allowed_domains_for_item(item)
            target_url = (item.get("artifact_url") or item.get("official_url") or "").strip()
            official_url = (item.get("official_url") or target_url).strip()
            if not target_url:
                raise ValueError(f"缺少 artifact_url/official_url: {item.get('title') or item.get('name')}")
            if not allowed_domains or not _domain_allowed(target_url, allowed_domains):
                raise ValueError(f"目标链接不在官方域名白名单内: {target_url}")

            request = Request(target_url, headers={"User-Agent": "Mozilla/5.0"})
            response = opener_factory().open(request, timeout=timeout)
            final_url = response.geturl()
            body = response.read()
            content_type = _content_type(response.headers)
            if not body:
                raise ValueError(f"官方链接返回空文件: {target_url}")
            if not _domain_allowed(final_url, allowed_domains):
                raise ValueError(f"最终跳转地址不在官方域名白名单内: {final_url}")

            if _is_pdf(final_url, content_type, body):
                file_type = "pdf"
                normalized_type = content_type or "application/pdf"
            elif _is_html(content_type, body):
                if _looks_like_error_page(body):
                    raise ValueError(f"疑似错误页/拦截页，不作为官方正文入库: {final_url}")
                file_type = "html"
                normalized_type = content_type or "text/html"
            else:
                raise ValueError(f"仅支持官方 PDF 或 HTML 正文页: {content_type or 'unknown'}")

            sha256 = hashlib.sha256(body).hexdigest()
            local_file = _safe_file_name(str(item.get("title") or item.get("name") or ""), final_url, sha256, file_type)
            (package_dir / local_file).write_bytes(body)
            manifest_rows.append(
                {
                    "source_record_id": item.get("source_record_id") or "",
                    "compliance_id": item.get("compliance_id") or item.get("id") or "",
                    "country_code": (item.get("country_code") or "ZZ").upper(),
                    "title": item.get("title") or item.get("name") or local_file,
                    "official_url": official_url,
                    "artifact_url": final_url,
                    "allowed_domains": allowed_domains,
                    "local_file": local_file,
                    "sha256": sha256,
                    "content_type": normalized_type,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "evidence_note": item.get("evidence_note") or "本地联网抓取官方原文，待服务器校验后入库。",
                }
            )
        except Exception as exc:
            if not continue_on_error:
                raise
            error_rows.append(
                {
                    "compliance_id": item.get("compliance_id") or item.get("id") or "",
                    "country_code": (item.get("country_code") or "ZZ").upper(),
                    "title": item.get("title") or item.get("name") or "",
                    "artifact_url": item.get("artifact_url") or item.get("official_url") or "",
                    "error": str(exc),
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    manifest_path = package_dir / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as fh:
        for row in manifest_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    if error_rows:
        with (package_dir / "manifest_errors.jsonl").open("w", encoding="utf-8") as fh:
            for row in error_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return manifest_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch official PDF/HTML artifacts locally and write a manifest package.")
    parser.add_argument("--input", required=True, help="Pending artifact JSONL/CSV exported from server.")
    parser.add_argument("--out", default="local_artifacts", help="Output directory for artifact package.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--continue-on-error", action="store_true", help="继续处理后续链接，并输出 manifest_errors.jsonl。")
    args = parser.parse_args()

    rows = fetch_artifacts(
        args.input,
        args.out,
        limit=args.limit,
        timeout=args.timeout,
        continue_on_error=args.continue_on_error,
    )
    print(json.dumps({"fetched": len(rows), "items": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
