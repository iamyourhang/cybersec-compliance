"""
collector/document/source_ingest.py
官方原文抓取桥接层：从 official_url 下载 PDF，上传到 COS，并创建 regulation_documents 记录。
"""

from __future__ import annotations

import hashlib
import logging
import re
import ssl
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Callable, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from collector.document.cos_storage import CosStorage
from collector.document.doc_repository import DocRepository
from config.settings import get_settings
from database.repository import ComplianceRepository, SourceArtifactRepository, SourceRecordRepository

logger = logging.getLogger(__name__)

PDF_SIGNATURE = b"%PDF"


@dataclass(frozen=True)
class DownloadedSource:
    source_url: str
    content: bytes
    file_name: str
    content_type: str
    sha256: str
    file_type: str


class _PdfLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]):
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value.strip())


class OfficialSourceFetcher:
    def __init__(self, opener_factory: Optional[Callable[[], object]] = None):
        self._ssl_context = ssl._create_unverified_context()
        self._opener_factory = opener_factory or (
            lambda: build_opener(HTTPRedirectHandler, HTTPSHandler(context=self._ssl_context))
        )

    def fetch_pdf(self, url: str, timeout: int = 20) -> DownloadedSource:
        return self.fetch_artifact(url, timeout=timeout, allow_html_fallback=False)

    def fetch_artifact(
        self,
        url: str,
        timeout: int = 20,
        allow_html_fallback: bool = False,
    ) -> DownloadedSource:
        final_url, body, content_type = self._open(url, timeout=timeout)
        self._ensure_non_empty(body, final_url)
        if self._is_pdf(body, content_type, final_url):
            return self._build_result(final_url, body, content_type, file_type="pdf")

        if "html" not in (content_type or "").lower():
            raise ValueError(f"官方链接不是 PDF/HTML: {content_type or 'unknown'}")

        for candidate in self._extract_pdf_links(final_url, body):
            try:
                nested_url, nested_body, nested_type = self._open(candidate, timeout=timeout)
                self._ensure_non_empty(nested_body, nested_url)
            except Exception as exc:
                logger.warning("跳过不可下载的官方 PDF 链接 [%s]: %s", candidate, exc)
                continue
            if self._is_pdf(nested_body, nested_type, nested_url):
                return self._build_result(nested_url, nested_body, nested_type, file_type="pdf")

        if allow_html_fallback:
            return self._build_result(final_url, body, content_type or "text/html", file_type="html")
        raise ValueError("官方链接页面未发现可下载的 PDF 原文")

    def _open(self, url: str, timeout: int = 20) -> tuple[str, bytes, str]:
        opener = self._opener_factory()
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            response = opener.open(request, timeout=timeout)
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            return response.geturl(), body, content_type
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ValueError(f"下载官方链接失败: {exc}") from exc

    def _is_pdf(self, body: bytes, content_type: str, final_url: str) -> bool:
        lowered = (content_type or "").lower()
        return (
            "application/pdf" in lowered
            or final_url.lower().endswith(".pdf")
            or body.startswith(PDF_SIGNATURE)
        )

    def _ensure_non_empty(self, body: bytes, final_url: str) -> None:
        if not body:
            raise ValueError(f"官方链接返回空文件: {final_url}")

    def _extract_pdf_links(self, base_url: str, html: bytes) -> Iterable[str]:
        parser = _PdfLinkParser()
        parser.feed(html.decode("utf-8", errors="ignore"))
        base_host = urlparse(base_url).netloc
        seen: set[str] = set()
        for href in parser.links:
            candidate = urljoin(base_url, href)
            parsed = urlparse(candidate)
            if parsed.scheme not in {"http", "https"}:
                continue
            if parsed.netloc != base_host:
                continue
            if ".pdf" not in parsed.path.lower() and "pdf" not in href.lower():
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            yield candidate

    def _build_result(self, source_url: str, content: bytes, content_type: str, file_type: str) -> DownloadedSource:
        file_name = PurePosixPath(urlparse(source_url).path).name or "official_source.pdf"
        if file_type == "pdf" and not file_name.lower().endswith(".pdf"):
            file_name = f"{file_name or 'official_source'}.pdf"
        if file_type == "html" and not file_name.lower().endswith(".html"):
            stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
            file_name = f"{stem or 'official_source'}.html"
        return DownloadedSource(
            source_url=source_url,
            content=content,
            file_name=file_name,
            content_type=content_type or "application/pdf",
            sha256=hashlib.sha256(content).hexdigest(),
            file_type=file_type,
        )


class OfficialSourceIngestService:
    def __init__(
        self,
        storage: Optional[CosStorage] = None,
        fetcher: Optional[OfficialSourceFetcher] = None,
        doc_repo=DocRepository,
        compliance_repo=ComplianceRepository,
        source_artifact_repo=SourceArtifactRepository,
        source_record_repo=SourceRecordRepository,
        settings=None,
    ):
        self._storage = storage or CosStorage()
        self._fetcher = fetcher or OfficialSourceFetcher()
        self._doc_repo = doc_repo
        self._compliance_repo = compliance_repo
        self._source_artifact_repo = source_artifact_repo
        self._source_record_repo = source_record_repo
        self._settings = settings or get_settings()

    def ingest_record(self, record: dict, requested_by: str = "system") -> dict:
        official_url = (
            record.get("official_url")
            or record.get("artifact_url")
            or record.get("source_url")
            or ""
        ).strip()
        if not official_url:
            raise ValueError("条目缺少 official_url，无法抓取官方原文")

        downloaded = self._fetcher.fetch_pdf(official_url)
        return self._store_downloaded_artifact(
            record=record,
            official_url=official_url,
            downloaded=downloaded,
            requested_by=requested_by,
        )

    def ingest_manual_source(
        self,
        record: dict,
        official_url: str,
        artifact_url: Optional[str] = None,
        requested_by: str = "system",
    ) -> dict:
        target_url = (artifact_url or official_url or "").strip()
        if not target_url:
            raise ValueError("缺少可下载的官方链接")
        downloaded = self._fetcher.fetch_artifact(target_url, allow_html_fallback=True)
        return self._store_downloaded_artifact(
            record=record,
            official_url=official_url,
            downloaded=downloaded,
            requested_by=requested_by,
        )

    def ingest_uploaded_source(
        self,
        record: dict,
        official_url: str,
        file_name: str,
        content: bytes,
        content_type: str,
        artifact_url: str | None = None,
        requested_by: str = "system",
    ) -> dict:
        file_type = "pdf" if self._is_pdf(content, content_type, file_name) else "html"
        downloaded = DownloadedSource(
            source_url=artifact_url or official_url,
            content=content,
            file_name=file_name,
            content_type=content_type or ("application/pdf" if file_type == "pdf" else "text/html"),
            sha256=hashlib.sha256(content).hexdigest(),
            file_type=file_type,
        )
        return self._store_downloaded_artifact(
            record=record,
            official_url=official_url,
            downloaded=downloaded,
            requested_by=requested_by,
        )

    def _is_pdf(self, body: bytes, content_type: str, file_name: str) -> bool:
        lowered = (content_type or "").lower()
        return (
            "application/pdf" in lowered
            or (file_name or "").lower().endswith(".pdf")
            or body.startswith(PDF_SIGNATURE)
        )

    def _store_downloaded_artifact(
        self,
        record: dict,
        official_url: str,
        downloaded: DownloadedSource,
        requested_by: str,
    ) -> dict:
        compliance_id = str(record["id"]) if record.get("id") and not record.get("source_status") else (
            str(record["compliance_id"]) if record.get("compliance_id") else None
        )
        source_record_id = record.get("source_record_id") or (str(record["id"]) if record.get("source_status") else None)
        country_code = (record.get("country_code") or "ZZ").upper()
        cos_key = (
            f"{self._settings.cos.report_prefix}documents/{country_code}/official_sources/"
            f"{downloaded.file_name}"
        )
        cos_url = self._storage.upload_bytes(downloaded.content, cos_key)

        doc_id = self._doc_repo.create(
            {
                "name": record.get("name") or record.get("title") or downloaded.file_name,
                "country_code": country_code,
                "file_name": downloaded.file_name,
                "cos_key": cos_key,
                "cos_url": cos_url,
                "file_size": len(downloaded.content),
                "file_type": downloaded.file_type,
                "uploaded_by": requested_by,
                "compliance_id": compliance_id,
            }
        )

        self._source_artifact_repo.upsert_for_compliance(
            compliance_id=compliance_id,
            official_url=official_url,
            artifact_url=downloaded.source_url,
            artifact_type=downloaded.content_type,
            artifact_sha256=downloaded.sha256,
            download_status="downloaded",
            download_error=None,
            document_id=doc_id,
            source_record_id=source_record_id,
        )
        if source_record_id and compliance_id:
            self._source_record_repo.attach_compliance(str(source_record_id), compliance_id)
        if compliance_id:
            self._compliance_repo.update(
                compliance_id,
                {
                    "official_url": official_url,
                    "source_document_id": doc_id,
                    "source_artifact_url": downloaded.source_url,
                    "source_artifact_type": downloaded.content_type,
                    "source_artifact_sha256": downloaded.sha256,
                    "source_download_status": "downloaded",
                    "source_download_error": None,
                },
                force=True,
            )

        return {
            "doc_id": doc_id,
            "cos_key": cos_key,
            "cos_url": cos_url,
            "source_url": downloaded.source_url,
            "sha256": downloaded.sha256,
            "file_name": downloaded.file_name,
            "file_type": downloaded.file_type,
        }
