from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from collector.official_sources.ai_fallback import OfficialSourceFallbackSearcher
from collector.official_sources.fetchers import OfficialSourceFetcher
from collector.official_sources.models import SyncStats
from collector.official_sources.relevance import is_cybersecurity_relevant
from collector.official_sources.repository import (
    OfficialSourceRepository,
    get_official_source_repository,
)
from database.repository import (
    ComplianceIndexRepository,
    ComplianceRepository,
    ReviewCaseRepository,
    SourceArtifactRepository,
    SourceRecordRepository,
)


class OfficialSourcePipeline:
    def __init__(
        self,
        source_repository: Optional[OfficialSourceRepository] = None,
        fetcher: Optional[OfficialSourceFetcher] = None,
        compliance_repository=ComplianceRepository,
        source_record_repository=SourceRecordRepository,
        source_artifact_repository=SourceArtifactRepository,
        fallback_searcher: Optional[OfficialSourceFallbackSearcher] = None,
    ):
        self._sources = source_repository or OfficialSourceRepository()
        self._fetcher = fetcher or OfficialSourceFetcher()
        self._compliance = compliance_repository
        self._source_records = source_record_repository
        self._source_artifacts = source_artifact_repository
        self._fallback_searcher = fallback_searcher or OfficialSourceFallbackSearcher()

    def sync_country_priorities(self, priorities: list[str]) -> dict[str, Any]:
        totals = {"source_count": 0, "discovered_count": 0, "candidate_count": 0}
        for source in self._sources.list_all(country_priorities=priorities, enabled_only=True):
            stats = self.sync_source(str(source["id"]))
            totals["source_count"] += 1
            totals["discovered_count"] += stats["discovered_count"]
            totals["candidate_count"] += stats["candidate_count"]
        return totals

    def sync_source(self, source_id: str) -> dict[str, Any]:
        source = self._sources.get_by_id(source_id)
        if not source:
            raise ValueError("官方源不存在")

        stats = SyncStats(source_id=source_id)
        try:
            items = self._fetcher.fetch(source)
            fallback_error = None
            history_status = "success"
            if not items:
                fallback_error = "抓取官方源失败: 官方源页面可访问，但未发现匹配结果"
                items = self._search_fallback_items(source, fallback_error)
                history_status = "success_fallback"
            stats.discovered_count = len(items)
            for item in items:
                if self._upsert_candidate(source, item):
                    stats.candidate_count += 1
            self._sources.record_history(
                source_id,
                history_status,
                discovered_count=stats.discovered_count,
                candidate_count=stats.candidate_count,
                artifact_count=stats.artifact_count,
                error=fallback_error,
            )
            return stats.to_dict()
        except Exception as exc:
            try:
                items = self._search_fallback_items(source, str(exc))
            except Exception:
                self._sources.record_history(source_id, "failed", error=str(exc))
                raise

            stats.discovered_count = len(items)
            for item in items:
                if self._upsert_candidate(source, item):
                    stats.candidate_count += 1
            self._sources.record_history(
                source_id,
                "success_fallback",
                discovered_count=stats.discovered_count,
                candidate_count=stats.candidate_count,
                artifact_count=stats.artifact_count,
                error=str(exc),
            )
            return stats.to_dict()

    def _upsert_candidate(self, source: dict[str, Any], item: dict[str, Any]) -> bool:
        title = (item.get("title") or "").strip()
        detail_url = (item.get("detail_url") or item.get("artifact_url") or "").strip()
        if not title or not detail_url:
            return False
        if not is_cybersecurity_relevant(f"{title} {detail_url} {item.get('summary') or ''}"):
            return False

        existing = self._compliance.find_existing(title, source["country_code"])
        entry_type_scope = source.get("entry_type_scope") or []
        entry_type = item.get("entry_type") or (entry_type_scope[0] if entry_type_scope else "regulation")
        compliance_id = str(existing["id"]) if existing else None
        source_record_id = self._source_records.upsert_candidate(
            country_code=source["country_code"],
            title=title,
            entry_type=entry_type,
            source_url=detail_url,
            artifact_url=item.get("artifact_url"),
            published_date=item.get("published_date"),
            official_source_id=str(source["id"]) if source.get("id") else None,
            compliance_id=compliance_id,
            discovery_method="official_source",
            source_payload={
                "source_name": source["name"],
                "summary": item.get("summary"),
                "detail_url": detail_url,
                "artifact_url": item.get("artifact_url"),
                "published_date": item.get("published_date"),
            },
        )
        self._source_artifacts.upsert_for_compliance(
            compliance_id=compliance_id,
            official_url=detail_url,
            artifact_url=item.get("artifact_url") or detail_url,
            artifact_type=None,
            artifact_sha256=None,
            download_status="pending",
            download_error=None,
            source_record_id=source_record_id,
        )
        if existing:
            ReviewCaseRepository.ensure_for_record(existing)
            ComplianceIndexRepository.refresh_for_compliance(existing)
        return True

    def _search_fallback_items(self, source: dict[str, Any], error_message: str) -> list[dict[str, Any]]:
        items = self._fallback_searcher.search(source, error_message=error_message)
        return [item for item in items if self._is_allowed_item(source, item)]

    def _is_allowed_item(self, source: dict[str, Any], item: dict[str, Any]) -> bool:
        allowed_domains = {
            self._normalize_domain(domain) for domain in (source.get("allowed_domains") or []) if domain
        }
        if not allowed_domains:
            return True
        urls = [item.get("detail_url") or "", item.get("artifact_url") or ""]
        valid_urls = [url for url in urls if url]
        if not valid_urls:
            return False
        return all(self._normalize_domain(urlparse(url).netloc) in allowed_domains for url in valid_urls)

    def _normalize_domain(self, domain: str) -> str:
        return (domain or "").strip().lower().removeprefix("www.")


def get_official_source_pipeline() -> OfficialSourcePipeline:
    return OfficialSourcePipeline(source_repository=get_official_source_repository())
