import json
import hashlib
from pathlib import Path

import pytest


class _FakeResponse:
    def __init__(self, url, body, content_type):
        self._url = url
        self._body = body
        self.headers = {"Content-Type": content_type}

    def read(self):
        return self._body

    def geturl(self):
        return self._url


def test_local_fetch_writes_manifest_with_sha256(tmp_path):
    from scripts.local_official_artifact_fetch import fetch_artifacts

    input_path = tmp_path / "pending.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "source_record_id": "src-1",
                "compliance_id": "comp-1",
                "country_code": "EU",
                "title": "Cyber Resilience Act",
                "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
                "artifact_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ:L_202402847",
                "allowed_domains": ["eur-lex.europa.eu"],
                "evidence_note": "official source",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    class _Opener:
        def open(self, request, timeout=20):
            return _FakeResponse(
                request.full_url,
                b"%PDF-1.7\nofficial",
                "application/pdf",
            )

    rows = fetch_artifacts(
        input_path=input_path,
        output_dir=tmp_path / "out",
        opener_factory=lambda: _Opener(),
        date_tag="20260428",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["sha256"] == hashlib.sha256(b"%PDF-1.7\nofficial").hexdigest()
    assert row["content_type"] == "application/pdf"
    assert row["local_file"].endswith(".pdf")
    assert (tmp_path / "out" / "20260428" / "manifest.jsonl").exists()
    assert (tmp_path / "out" / "20260428" / row["local_file"]).read_bytes() == b"%PDF-1.7\nofficial"


def test_local_fetch_rejects_non_official_redirect(tmp_path):
    from scripts.local_official_artifact_fetch import fetch_artifacts

    input_path = tmp_path / "pending.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "country_code": "EU",
                "title": "Bad Redirect",
                "official_url": "https://eur-lex.europa.eu/source",
                "artifact_url": "https://eur-lex.europa.eu/source",
                "allowed_domains": ["eur-lex.europa.eu"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    class _Opener:
        def open(self, request, timeout=20):
            return _FakeResponse(
                "https://example-cdn.invalid/file.pdf",
                b"%PDF-1.7\nwrong",
                "application/pdf",
            )

    with pytest.raises(ValueError, match="官方域名"):
        fetch_artifacts(
            input_path=input_path,
            output_dir=tmp_path / "out",
            opener_factory=lambda: _Opener(),
            date_tag="20260428",
        )


def test_local_fetch_continue_on_error_writes_error_manifest(tmp_path):
    from scripts.local_official_artifact_fetch import fetch_artifacts

    input_path = tmp_path / "pending.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "compliance_id": "bad-1",
                        "country_code": "EU",
                        "title": "Bad Redirect",
                        "official_url": "https://eur-lex.europa.eu/source",
                        "artifact_url": "https://eur-lex.europa.eu/source",
                        "allowed_domains": ["eur-lex.europa.eu"],
                    }
                ),
                json.dumps(
                    {
                        "compliance_id": "good-1",
                        "country_code": "EU",
                        "title": "Good PDF",
                        "official_url": "https://eur-lex.europa.eu/ok.pdf",
                        "artifact_url": "https://eur-lex.europa.eu/ok.pdf",
                        "allowed_domains": ["eur-lex.europa.eu"],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class _Opener:
        def open(self, request, timeout=20):
            if request.full_url.endswith("source"):
                return _FakeResponse("https://example.invalid/file.pdf", b"%PDF-1.7\nbad", "application/pdf")
            return _FakeResponse(request.full_url, b"%PDF-1.7\ngood", "application/pdf")

    rows = fetch_artifacts(
        input_path=input_path,
        output_dir=tmp_path / "out",
        opener_factory=lambda: _Opener(),
        date_tag="20260428",
        continue_on_error=True,
    )

    assert [row["compliance_id"] for row in rows] == ["good-1"]
    error_path = tmp_path / "out" / "20260428" / "manifest_errors.jsonl"
    errors = [json.loads(line) for line in error_path.read_text(encoding="utf-8").splitlines()]
    assert errors[0]["compliance_id"] == "bad-1"
    assert "官方域名" in errors[0]["error"]


def test_export_rows_include_allowed_domains_and_prioritize_failed_records():
    from scripts.export_pending_artifacts import build_export_rows

    rows = build_export_rows(
        compliance_records=[
            {
                "id": "comp-1",
                "country_code": "EU",
                "name": "CRA",
                "entry_type": "regulation",
                "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
                "source_download_status": "failed",
                "source_download_error": "timeout",
                "data_source": "official_source:EUR-Lex",
            }
        ],
        source_records=[
            {
                "id": "src-1",
                "compliance_id": None,
                "country_code": "UK",
                "title": "PSTI",
                "entry_type": "regulation",
                "source_url": "https://www.gov.uk/psti",
                "artifact_url": None,
                "download_status": "pending",
            }
        ],
        official_sources=[
            {"country_code": "EU", "name": "EUR-Lex", "allowed_domains": ["eur-lex.europa.eu"], "priority": 1},
            {"country_code": "UK", "name": "GOV.UK", "allowed_domains": ["gov.uk"], "priority": 2},
        ],
        limit=10,
    )

    assert [row["title"] for row in rows] == ["CRA", "PSTI"]
    assert rows[0]["source_kind"] == "compliance"
    assert rows[0]["allowed_domains"] == ["eur-lex.europa.eu"]
    assert rows[0]["evidence_note"].startswith("待本地联网补源")
    assert rows[1]["source_record_id"] == "src-1"
    assert rows[1]["allowed_domains"] == ["gov.uk"]


def test_export_rows_exclude_official_but_non_cybersecurity_records():
    from scripts.export_pending_artifacts import build_export_rows

    rows = build_export_rows(
        compliance_records=[],
        source_records=[
            {
                "id": "src-spectrum",
                "country_code": "ZA",
                "title": "Spectrum Assignments Licences Type Approval Broadcast Quarter 1",
                "entry_type": "certification",
                "source_url": "https://www.icasa.org.za/spectrum-assignments-licences-type-approval-broadcast-quarter-1",
                "artifact_url": None,
                "download_status": "pending",
            },
            {
                "id": "src-cyber",
                "country_code": "KR",
                "title": "IoT Security Certification",
                "entry_type": "certification",
                "source_url": "https://www.kisa.or.kr/1050608",
                "artifact_url": None,
                "download_status": "pending",
            },
        ],
        official_sources=[
            {"country_code": "ZA", "name": "ICASA", "allowed_domains": ["icasa.org.za"], "priority": 1},
            {"country_code": "KR", "name": "KISA", "allowed_domains": ["kisa.or.kr"], "priority": 1},
        ],
        limit=10,
    )

    assert [row["source_record_id"] for row in rows] == ["src-cyber"]


def test_import_manifest_validates_sha_and_does_not_mark_verified(tmp_path):
    from scripts.import_local_artifacts import import_artifact_manifest

    artifact_dir = tmp_path / "package"
    artifact_dir.mkdir()
    artifact_path = artifact_dir / "law.pdf"
    artifact_path.write_bytes(b"%PDF-1.7\nbridge")
    manifest_path = artifact_dir / "manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "source_record_id": "src-1",
                "compliance_id": "comp-1",
                "country_code": "EU",
                "title": "CRA",
                "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
                "artifact_url": "https://eur-lex.europa.eu/file.pdf",
                "allowed_domains": ["eur-lex.europa.eu"],
                "local_file": "law.pdf",
                "sha256": hashlib.sha256(b"%PDF-1.7\nbridge").hexdigest(),
                "content_type": "application/pdf",
                "evidence_note": "official PDF fetched locally",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    calls = {}

    class _ComplianceRepo:
        @staticmethod
        def get_by_id(record_id):
            calls["get_by_id"] = record_id
            return {
                "id": record_id,
                "name": "CRA",
                "country_code": "EU",
                "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
                "authenticity_status": "suspicious",
            }

        @staticmethod
        def set_authenticity_review(*args, **kwargs):
            raise AssertionError("batch artifact import must not mark records verified")

    class _Ingest:
        def ingest_uploaded_source(self, record, official_url, file_name, content, content_type, requested_by, artifact_url=None):
            calls["ingest"] = {
                "record": record,
                "official_url": official_url,
                "artifact_url": artifact_url,
                "file_name": file_name,
                "content": content,
                "content_type": content_type,
                "requested_by": requested_by,
            }
            return {"doc_id": "doc-1", "file_type": "pdf", "sha256": "4e55e9128f13c822545924f9313af900b2016fa7ff10c0ead388addd951410c3"}

    results = import_artifact_manifest(
        manifest_path=manifest_path,
        artifact_dir=artifact_dir,
        compliance_repo=_ComplianceRepo,
        ingest_service=_Ingest(),
        requested_by="bridge-test",
        parse_pdf=False,
    )

    assert results == [{"status": "imported", "doc_id": "doc-1", "title": "CRA"}]
    assert calls["get_by_id"] == "comp-1"
    assert calls["ingest"]["official_url"] == "https://eur-lex.europa.eu/eli/reg/2024/2847/oj"
    assert calls["ingest"]["artifact_url"] == "https://eur-lex.europa.eu/file.pdf"
    assert calls["ingest"]["content"] == b"%PDF-1.7\nbridge"


def test_import_manifest_parses_and_indexes_html_artifacts(tmp_path, monkeypatch):
    from scripts.import_local_artifacts import import_artifact_manifest

    artifact_dir = tmp_path / "package"
    artifact_dir.mkdir()
    body = b"<!doctype html><html><body><h1>Cybersecurity Act</h1><p>Official text.</p></body></html>"
    artifact_path = artifact_dir / "law.html"
    artifact_path.write_bytes(body)
    manifest_path = artifact_dir / "manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "compliance_id": "comp-1",
                "country_code": "EU",
                "title": "Cybersecurity Act",
                "official_url": "https://op.europa.eu/en/publication-detail/example",
                "artifact_url": "https://publications.europa.eu/resource/cellar/example/DOC_1",
                "allowed_domains": ["op.europa.eu", "publications.europa.eu"],
                "local_file": "law.html",
                "sha256": hashlib.sha256(body).hexdigest(),
                "content_type": "application/xhtml+xml;charset=UTF-8",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    calls = []

    class _ComplianceRepo:
        @staticmethod
        def get_by_id(record_id):
            return {
                "id": record_id,
                "name": "Cybersecurity Act",
                "country_code": "EU",
                "authenticity_status": "verified",
            }

    class _Ingest:
        def ingest_uploaded_source(self, record, official_url, file_name, content, content_type, requested_by, artifact_url=None):
            return {"doc_id": "doc-html", "file_type": "html", "sha256": hashlib.sha256(content).hexdigest()}

    class _FakeParseService:
        def parse_document(self, doc_id, write_to_knowledge=False):
            calls.append(("parse", doc_id, write_to_knowledge))
            return {"success": True}

    class _FakeIndexService:
        def index_document(self, doc_id):
            calls.append(("index", doc_id))
            return {"chunk_count": 1}

    monkeypatch.setattr("collector.document.parse_service.DocumentParseService", _FakeParseService)
    monkeypatch.setattr("collector.document.index_service.DocumentIndexService", _FakeIndexService)

    results = import_artifact_manifest(
        manifest_path=manifest_path,
        artifact_dir=artifact_dir,
        compliance_repo=_ComplianceRepo,
        ingest_service=_Ingest(),
        parse_pdf=True,
    )

    assert results == [{"status": "imported", "doc_id": "doc-html", "title": "Cybersecurity Act"}]
    assert calls == [("parse", "doc-html", False), ("index", "doc-html")]


def test_import_manifest_rejects_hash_mismatch(tmp_path):
    from scripts.import_local_artifacts import import_artifact_manifest

    artifact_dir = tmp_path / "package"
    artifact_dir.mkdir()
    (artifact_dir / "law.pdf").write_bytes(b"%PDF-1.7\nchanged")
    manifest_path = artifact_dir / "manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "country_code": "EU",
                "title": "CRA",
                "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
                "allowed_domains": ["eur-lex.europa.eu"],
                "local_file": "law.pdf",
                "sha256": "not-the-real-hash",
                "content_type": "application/pdf",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="SHA256"):
        import_artifact_manifest(manifest_path=manifest_path, artifact_dir=artifact_dir, parse_pdf=False)
