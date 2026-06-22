from collector.document.source_ingest import OfficialSourceFetcher, OfficialSourceIngestService


class _FakeResponse:
    def __init__(self, url, body, content_type="application/pdf", status=200):
        self._url = url
        self._body = body
        self.status = status
        self.headers = {"Content-Type": content_type}

    def read(self):
        return self._body

    def geturl(self):
        return self._url


def test_official_source_fetcher_accepts_direct_pdf():
    pdf_bytes = b"%PDF-1.7\nfake"

    class _Opener:
        def open(self, request, timeout=20):
            return _FakeResponse(
                "https://example.com/regulation.pdf",
                pdf_bytes,
                content_type="application/pdf",
            )

    fetcher = OfficialSourceFetcher(opener_factory=lambda: _Opener())
    result = fetcher.fetch_pdf("https://example.com/regulation.pdf")

    assert result.source_url == "https://example.com/regulation.pdf"
    assert result.content == pdf_bytes
    assert result.file_name == "regulation.pdf"
    assert result.content_type == "application/pdf"
    assert len(result.sha256) == 64


def test_official_source_fetcher_rejects_empty_pdf_response():
    class _Opener:
        def open(self, request, timeout=20):
            return _FakeResponse(
                "https://example.com/regulation.pdf",
                b"",
                content_type="application/pdf",
            )

    fetcher = OfficialSourceFetcher(opener_factory=lambda: _Opener())

    try:
        fetcher.fetch_pdf("https://example.com/regulation.pdf")
    except ValueError as exc:
        assert "空文件" in str(exc)
    else:
        raise AssertionError("empty PDF response should be rejected")


def test_official_source_fetcher_follows_pdf_link_from_html():
    html = b"""
    <html><body>
      <a href="/files/official-law.pdf">Download PDF</a>
    </body></html>
    """
    pdf_bytes = b"%PDF-1.4\nlinked"

    class _Opener:
        def __init__(self):
            self.calls = []

        def open(self, request, timeout=20):
            self.calls.append(request.full_url)
            if request.full_url == "https://example.com/source":
                return _FakeResponse(
                    "https://example.com/source",
                    html,
                    content_type="text/html; charset=utf-8",
                )
            if request.full_url == "https://example.com/files/official-law.pdf":
                return _FakeResponse(
                    "https://example.com/files/official-law.pdf",
                    pdf_bytes,
                    content_type="application/pdf",
                )
            raise AssertionError(f"unexpected url {request.full_url}")

    opener = _Opener()
    fetcher = OfficialSourceFetcher(opener_factory=lambda: opener)
    result = fetcher.fetch_pdf("https://example.com/source")

    assert opener.calls == [
        "https://example.com/source",
        "https://example.com/files/official-law.pdf",
    ]
    assert result.file_name == "official-law.pdf"
    assert result.content == pdf_bytes


def test_official_source_fetcher_falls_back_to_html_when_pdf_link_fails():
    html = b"""
    <html><body>
      <h1>Official Cybersecurity Directions</h1>
      <a href="/PDF/old-dead-link.pdf">Directions PDF</a>
    </body></html>
    """

    class _Opener:
        def open(self, request, timeout=20):
            if request.full_url == "https://official.example.com/directions":
                return _FakeResponse(
                    "https://official.example.com/directions",
                    html,
                    content_type="text/html; charset=utf-8",
                )
            raise ValueError("404")

    fetcher = OfficialSourceFetcher(opener_factory=lambda: _Opener())
    result = fetcher.fetch_artifact("https://official.example.com/directions", allow_html_fallback=True)

    assert result.file_type == "html"
    assert result.source_url == "https://official.example.com/directions"
    assert result.content == html


def test_official_source_ingest_creates_document_and_updates_record():
    uploaded = {}
    created = {}
    updated = {}
    artifacts = {}

    class _Storage:
        def upload_bytes(self, data, cos_key):
            uploaded["data"] = data
            uploaded["cos_key"] = cos_key
            return f"https://cos.example.com/{cos_key}"

    class _Fetcher:
        def fetch_pdf(self, url):
            return type(
                "Fetched",
                (),
                {
                    "source_url": "https://official.example.com/files/law.pdf",
                    "content": b"%PDF-1.4\nsource",
                    "file_name": "law.pdf",
                    "file_type": "pdf",
                    "content_type": "application/pdf",
                    "sha256": "a" * 64,
                },
            )()

    class _DocRepo:
        @staticmethod
        def create(data):
            created["data"] = data
            return "doc-123"

    class _ComplianceRepo:
        @staticmethod
        def update(record_id, data, version_bump=True, force=False):
            updated["record_id"] = record_id
            updated["data"] = data
            return True

    class _ArtifactRepo:
        @staticmethod
        def upsert_for_compliance(**kwargs):
            artifacts["payload"] = kwargs
            return "artifact-1"

    class _SourceRecordRepo:
        @staticmethod
        def attach_compliance(source_record_id, compliance_id):
            raise AssertionError("should not attach compliance for direct compliance record")

    service = OfficialSourceIngestService(
        storage=_Storage(),
        fetcher=_Fetcher(),
        doc_repo=_DocRepo,
        compliance_repo=_ComplianceRepo,
        source_artifact_repo=_ArtifactRepo,
        source_record_repo=_SourceRecordRepo,
        settings=type("S", (), {"cos": type("Cos", (), {"report_prefix": "reports/"})()})(),
    )

    result = service.ingest_record(
        {
            "id": "rec-1",
            "name": "Cyber Resilience Act",
            "country_code": "EU",
            "official_url": "https://official.example.com/page",
        },
        requested_by="tester",
    )

    assert result["doc_id"] == "doc-123"
    assert result["cos_url"] == "https://cos.example.com/reports/documents/EU/official_sources/law.pdf"
    assert created["data"]["compliance_id"] == "rec-1"
    assert created["data"]["uploaded_by"] == "tester"
    assert updated["record_id"] == "rec-1"
    assert updated["data"]["source_document_id"] == "doc-123"
    assert updated["data"]["source_download_status"] == "downloaded"
    assert updated["data"]["source_artifact_url"] == "https://official.example.com/files/law.pdf"
    assert artifacts["payload"]["document_id"] == "doc-123"
    assert artifacts["payload"]["download_status"] == "downloaded"


def test_official_source_ingest_accepts_uploaded_html_source():
    uploaded = {}
    created = {}
    updated = {}
    artifacts = {}

    class _Storage:
        def upload_bytes(self, data, cos_key):
            uploaded["data"] = data
            uploaded["cos_key"] = cos_key
            return f"https://cos.example.com/{cos_key}"

    class _DocRepo:
        @staticmethod
        def create(data):
            created["data"] = data
            return "doc-html"

    class _ComplianceRepo:
        @staticmethod
        def update(record_id, data, version_bump=True, force=False):
            updated["record_id"] = record_id
            updated["data"] = data
            return True

    class _ArtifactRepo:
        @staticmethod
        def upsert_for_compliance(**kwargs):
            artifacts["payload"] = kwargs
            return "artifact-html"

    class _SourceRecordRepo:
        @staticmethod
        def attach_compliance(source_record_id, compliance_id):
            raise AssertionError("should not attach compliance for direct compliance record")

    service = OfficialSourceIngestService(
        storage=_Storage(),
        doc_repo=_DocRepo,
        compliance_repo=_ComplianceRepo,
        source_artifact_repo=_ArtifactRepo,
        source_record_repo=_SourceRecordRepo,
        settings=type("S", (), {"cos": type("Cos", (), {"report_prefix": "reports/"})()})(),
    )

    result = service.ingest_uploaded_source(
        {
            "id": "rec-html",
            "name": "Official HTML Guidance",
            "country_code": "CA",
            "official_url": "https://example.com/guidance",
        },
        official_url="https://example.com/guidance",
        artifact_url="https://example.com/files/guidance.html",
        file_name="guidance.html",
        content=b"<html><body><h1>Official Guidance</h1></body></html>",
        content_type="text/html",
        requested_by="tester",
    )

    assert result["doc_id"] == "doc-html"
    assert created["data"]["file_type"] == "html"
    assert updated["data"]["source_document_id"] == "doc-html"
    assert updated["data"]["source_artifact_url"] == "https://example.com/files/guidance.html"
    assert result["source_url"] == "https://example.com/files/guidance.html"
    assert artifacts["payload"]["artifact_type"] == "text/html"
