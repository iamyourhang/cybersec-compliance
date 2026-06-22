from collector.official_sources.pipeline import OfficialSourcePipeline
from collector.official_sources.fetchers import OfficialSourceFetcher


class _FakeSourceRepo:
    def __init__(self, source):
        self.source = source
        self.history = []

    def get_by_id(self, source_id):
        assert source_id == self.source["id"]
        return self.source

    def record_history(self, source_id, status, discovered_count=0, candidate_count=0, artifact_count=0, error=None):
        self.history.append(
            {
                "source_id": source_id,
                "status": status,
                "discovered_count": discovered_count,
                "candidate_count": candidate_count,
                "artifact_count": artifact_count,
                "error": error,
            }
        )


class _FakeFetcher:
    def fetch(self, source):
        return [
            {
                "title": "Cyber Resilience Act",
                "detail_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
                "published_date": "2024-10-23",
            }
        ]


class _FakeComplianceRepo:
    def __init__(self, existing=None):
        self.existing = existing

    def find_existing(self, name, country_code):
        return self.existing


class _FakeSourceRecordRepo:
    def __init__(self):
        self.items = []

    def upsert_candidate(self, **payload):
        self.items.append(payload)
        return "src-rec-1"


class _FakeArtifactRepo:
    def __init__(self):
        self.items = []

    def upsert_for_compliance(self, **payload):
        self.items.append(payload)
        return "src-art-1"


class _FailingFetcher:
    def fetch(self, source):
        raise ValueError("抓取官方源失败: timeout")


class _TrackingFallbackSearcher:
    def __init__(self, items=None):
        self.items = items or []
        self.calls = []

    def search(self, source, error_message=None):
        self.calls.append({"source": source, "error_message": error_message})
        return list(self.items)


def test_sync_source_creates_candidate_record():
    source = {
        "id": "src-1",
        "name": "EUR-Lex",
        "country_code": "EU",
        "entry_type_scope": ["regulation"],
    }
    repo = _FakeSourceRepo(source)
    compliance_repo = _FakeComplianceRepo()
    source_record_repo = _FakeSourceRecordRepo()
    artifact_repo = _FakeArtifactRepo()
    pipeline = OfficialSourcePipeline(
        source_repository=repo,
        fetcher=_FakeFetcher(),
        compliance_repository=compliance_repo,
        source_record_repository=source_record_repo,
        source_artifact_repository=artifact_repo,
    )

    result = pipeline.sync_source("src-1")

    assert result["discovered_count"] == 1
    assert result["candidate_count"] == 1
    assert source_record_repo.items[0]["title"] == "Cyber Resilience Act"
    assert source_record_repo.items[0]["discovery_method"] == "official_source"
    assert artifact_repo.items[0]["download_status"] == "pending"
    assert repo.history[0]["status"] == "success"


def test_fetcher_normalizes_www_domains():
    fetcher = OfficialSourceFetcher()

    assert fetcher._normalize_domain("www.csa.gov.sg") == "csa.gov.sg"
    assert fetcher._normalize_domain("csa.gov.sg") == "csa.gov.sg"


def test_fetcher_rejects_official_but_non_cybersecurity_equipment_links():
    fetcher = OfficialSourceFetcher()

    assert fetcher._is_cybersecurity_relevant(
        "Spectrum Assignments Licences Type Approval Broadcast Quarter 1 "
        "https://www.icasa.org.za/spectrum-assignments-licences-type-approval-broadcast-quarter-1"
    ) is False
    assert fetcher._is_cybersecurity_relevant(
        "Cybersecurity Labelling Scheme for IoT "
        "https://www.csa.gov.sg/our-programmes/certification-and-labelling-schemes/cybersecurity-labelling-scheme"
    ) is True


def test_fetcher_accepts_direct_pdf_index_source(monkeypatch):
    fetcher = OfficialSourceFetcher()
    monkeypatch.setattr(fetcher, "_open", lambda url: b"%PDF-1.7\ncybersecurity law")

    items = fetcher.fetch(
        {
            "name": "Hong Kong Critical Infrastructure Computer Systems Bill",
            "base_url": "https://www.legco.gov.hk",
            "list_url": "https://www.legco.gov.hk/yr2024/english/bills/b202412061.pdf",
            "source_type": "pdf_index",
            "allowed_domains": ["legco.gov.hk"],
            "entry_type_scope": ["regulation"],
        }
    )

    assert items == [
        {
            "title": "Hong Kong Critical Infrastructure Computer Systems Bill",
            "detail_url": "https://www.legco.gov.hk/yr2024/english/bills/b202412061.pdf",
            "published_date": None,
            "artifact_url": "https://www.legco.gov.hk/yr2024/english/bills/b202412061.pdf",
            "summary": None,
            "issuing_body": None,
            "entry_type": None,
        }
    ]


def test_fetcher_can_include_official_html_page_itself(monkeypatch):
    fetcher = OfficialSourceFetcher()
    monkeypatch.setattr(fetcher, "_open", lambda url: b"<html><body>Cybersecurity Act official page</body></html>")

    items = fetcher.fetch(
        {
            "name": "Thailand Cybersecurity Act",
            "base_url": "https://www.mdes.go.th",
            "list_url": "https://www.mdes.go.th/law/detail/1904-Cybersecurity-Act--B-E--2562--2019-",
            "source_type": "html_list",
            "allowed_domains": ["mdes.go.th"],
            "entry_type_scope": ["regulation"],
            "parser_config": {"include_self": True, "self_title": "Cybersecurity Act B.E. 2562 (2019)"},
        }
    )

    assert items[0]["title"] == "Cybersecurity Act B.E. 2562 (2019)"
    assert items[0]["detail_url"] == "https://www.mdes.go.th/law/detail/1904-Cybersecurity-Act--B-E--2562--2019-"
    assert items[0]["artifact_url"] is None


def test_sync_source_uses_ai_fallback_when_fetch_fails():
    source = {
        "id": "src-1",
        "name": "CSA Singapore",
        "country_code": "SG",
        "base_url": "https://www.csa.gov.sg",
        "allowed_domains": ["csa.gov.sg"],
        "entry_type_scope": ["certification"],
    }
    repo = _FakeSourceRepo(source)
    compliance_repo = _FakeComplianceRepo()
    source_record_repo = _FakeSourceRecordRepo()
    artifact_repo = _FakeArtifactRepo()
    fallback = _TrackingFallbackSearcher(
        items=[
            {
                "title": "Cybersecurity Labelling Scheme for IoT",
                "detail_url": "https://www.csa.gov.sg/our-programmes/certification-and-labelling-schemes/cybersecurity-labelling-scheme/",
                "artifact_url": "https://www.csa.gov.sg/docs/default-source/certification-and-labelling-schemes/cls-iot.pdf",
                "published_date": "2025-01-10",
            }
        ]
    )
    pipeline = OfficialSourcePipeline(
        source_repository=repo,
        fetcher=_FailingFetcher(),
        compliance_repository=compliance_repo,
        source_record_repository=source_record_repo,
        source_artifact_repository=artifact_repo,
        fallback_searcher=fallback,
    )

    result = pipeline.sync_source("src-1")

    assert result["discovered_count"] == 1
    assert result["candidate_count"] == 1
    assert len(fallback.calls) == 1
    assert repo.history[0]["status"] == "success_fallback"
    assert "timeout" in (repo.history[0]["error"] or "")
    assert source_record_repo.items[0]["source_url"].startswith("https://www.csa.gov.sg/")


def test_sync_source_does_not_use_ai_fallback_when_fetch_succeeds():
    source = {
        "id": "src-1",
        "name": "EUR-Lex",
        "country_code": "EU",
        "allowed_domains": ["eur-lex.europa.eu"],
        "entry_type_scope": ["regulation"],
    }
    repo = _FakeSourceRepo(source)
    compliance_repo = _FakeComplianceRepo()
    source_record_repo = _FakeSourceRecordRepo()
    artifact_repo = _FakeArtifactRepo()
    fallback = _TrackingFallbackSearcher(
        items=[
            {
                "title": "Should Not Be Used",
                "detail_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
            }
        ]
    )
    pipeline = OfficialSourcePipeline(
        source_repository=repo,
        fetcher=_FakeFetcher(),
        compliance_repository=compliance_repo,
        source_record_repository=source_record_repo,
        source_artifact_repository=artifact_repo,
        fallback_searcher=fallback,
    )

    result = pipeline.sync_source("src-1")

    assert result["discovered_count"] == 1
    assert result["candidate_count"] == 1
    assert fallback.calls == []
    assert repo.history[0]["status"] == "success"


def test_sync_source_rejects_ai_fallback_results_outside_allowed_domains():
    source = {
        "id": "src-1",
        "name": "CSA Singapore",
        "country_code": "SG",
        "base_url": "https://www.csa.gov.sg",
        "allowed_domains": ["csa.gov.sg"],
        "entry_type_scope": ["certification"],
    }
    repo = _FakeSourceRepo(source)
    compliance_repo = _FakeComplianceRepo()
    source_record_repo = _FakeSourceRecordRepo()
    artifact_repo = _FakeArtifactRepo()
    fallback = _TrackingFallbackSearcher(
        items=[
            {
                "title": "Bad Mirror Copy",
                "detail_url": "https://example.com/cls-iot",
                "artifact_url": "https://mirror.example.com/cls-iot.pdf",
            }
        ]
    )
    pipeline = OfficialSourcePipeline(
        source_repository=repo,
        fetcher=_FailingFetcher(),
        compliance_repository=compliance_repo,
        source_record_repository=source_record_repo,
        source_artifact_repository=artifact_repo,
        fallback_searcher=fallback,
    )

    result = pipeline.sync_source("src-1")

    assert result["discovered_count"] == 0
    assert result["candidate_count"] == 0
    assert source_record_repo.items == []
    assert repo.history[0]["status"] == "success_fallback"


def test_sync_source_links_existing_record_without_mutating_knowledge(monkeypatch):
    source = {
        "id": "src-1",
        "name": "EUR-Lex",
        "country_code": "EU",
        "entry_type_scope": ["regulation"],
    }
    repo = _FakeSourceRepo(source)
    compliance_repo = _FakeComplianceRepo(existing={"id": "rec-1", "country_code": "EU", "name": "Cyber Resilience Act"})
    source_record_repo = _FakeSourceRecordRepo()
    artifact_repo = _FakeArtifactRepo()
    ensured = {}
    refreshed = {}
    monkeypatch.setattr(
        "collector.official_sources.pipeline.ReviewCaseRepository.ensure_for_record",
        lambda record: ensured.update({"record": record}) or "case-1",
    )
    monkeypatch.setattr(
        "collector.official_sources.pipeline.ComplianceIndexRepository.refresh_for_compliance",
        lambda record: refreshed.update({"record": record}) or "idx-1",
    )
    pipeline = OfficialSourcePipeline(
        source_repository=repo,
        fetcher=_FakeFetcher(),
        compliance_repository=compliance_repo,
        source_record_repository=source_record_repo,
        source_artifact_repository=artifact_repo,
    )

    result = pipeline.sync_source("src-1")

    assert result["candidate_count"] == 1
    assert source_record_repo.items[0]["compliance_id"] == "rec-1"
    assert artifact_repo.items[0]["compliance_id"] == "rec-1"
    assert ensured["record"]["id"] == "rec-1"
    assert refreshed["record"]["id"] == "rec-1"


def test_fetcher_filters_navigation_feeds_and_spreadsheets(monkeypatch):
    html = b"""
    <html><body>
      <a href="/pubs/ir/8259/final">Good Final Rule</a>
      <a href="/Publications">View All Publications</a>
      <a href="/feeds/security.rss">RSS Feed</a>
      <a href="/files/catalog.xlsx">Download XLSX</a>
      <a href="/files/export.json">JSON Export</a>
    </body></html>
    """
    fetcher = OfficialSourceFetcher()
    monkeypatch.setattr(fetcher, "_open", lambda url: html)

    items = fetcher._fetch_html_like(
        {
            "name": "NIST CSRC",
            "base_url": "https://csrc.nist.gov",
            "list_url": "https://csrc.nist.gov/Publications",
            "allowed_domains": ["csrc.nist.gov"],
            "parser_config": {
                "url_patterns": ["/pubs/", "/Publications"],
                "exclude_url_patterns": ["/feeds/", "\\.rss$", "\\.json$", "\\.xlsx$", "/Publications/?$"],
                "exclude_title_patterns": ["view all", "rss", "json", "xlsx"],
            },
        },
        pdf_only=False,
    )

    assert len(items) == 1
    assert items[0]["title"] == "Good Final Rule"
    assert items[0]["detail_url"] == "https://csrc.nist.gov/pubs/ir/8259/final"


def test_fetcher_filters_generic_navigation_anchors(monkeypatch):
    html = b"""
    <html><body>
      <a href="#top">TOP</a>
      <a href="#menu">Menu</a>
      <a href="#search">Search</a>
      <a href="/certified-products">Certified Products</a>
    </body></html>
    """
    fetcher = OfficialSourceFetcher()
    monkeypatch.setattr(fetcher, "_open", lambda url: html)

    items = fetcher._fetch_html_like(
        {
            "name": "Certification Body",
            "base_url": "https://cert.example.gov",
            "list_url": "https://cert.example.gov/scheme",
            "allowed_domains": ["cert.example.gov"],
            "parser_config": {
                "url_patterns": ["TOP", "Menu", "Search", "Certified Products"],
            },
        },
        pdf_only=False,
    )

    assert [item["title"] for item in items] == ["Certified Products"]
