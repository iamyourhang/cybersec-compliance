import hashlib

from scripts import import_curated_official_docs as importer


def test_curated_import_uses_local_file_when_available(tmp_path, monkeypatch):
    local_pdf = tmp_path / "official.pdf"
    body = b"%PDF-1.4\nofficial"
    local_pdf.write_bytes(body)

    item = {
        "name": "Official Cybersecurity Framework",
        "country_code": "UY",
        "entry_type": "standard",
        "mandatory": "recommended",
        "official_url": "https://www.gub.uy/source",
        "artifact_url": "https://www.gub.uy/file.pdf",
        "evidence_note": "official evidence",
        "local_file": str(local_pdf),
    }

    monkeypatch.setattr(
        importer.ComplianceRepository,
        "find_existing",
        lambda name, country_code: {
            "id": "comp-1",
            "name": name,
            "country_code": country_code,
        },
    )

    captured = {}

    class _FakeIngest:
        def ingest_uploaded_source(
            self,
            record,
            official_url,
            file_name,
            content,
            content_type,
            requested_by,
            artifact_url=None,
        ):
            captured["upload"] = {
                "record": record,
                "official_url": official_url,
                "file_name": file_name,
                "content": content,
                "content_type": content_type,
                "requested_by": requested_by,
                "artifact_url": artifact_url,
            }
            return {
                "doc_id": "doc-1",
                "cos_url": "cos://official.pdf",
                "sha256": hashlib.sha256(content).hexdigest(),
                "file_type": "pdf",
            }

        def ingest_manual_source(self, *args, **kwargs):
            raise AssertionError("local_file should avoid server-side fetching")

    class _FakeReview:
        def register_manual_source(
            self,
            record,
            ingest_result,
            official_url,
            evidence_note,
            checked_by,
        ):
            return {
                "canonical_requirement_id": "canon-1",
                "review_case_id": "review-1",
            }

    monkeypatch.setattr(importer, "OfficialSourceIngestService", lambda: _FakeIngest())
    monkeypatch.setattr(importer, "AuthenticityReviewService", lambda: _FakeReview())

    result = importer.process_item(item, parse_docs=False, generate_spec=False)

    assert result["doc_id"] == "doc-1"
    assert captured["upload"]["content"] == body
    assert captured["upload"]["content_type"] == "application/pdf"
    assert captured["upload"]["artifact_url"] == "https://www.gub.uy/file.pdf"


def test_curated_import_rejects_pdf_path_when_body_is_not_pdf(tmp_path, monkeypatch):
    local_pdf = tmp_path / "official.pdf"
    local_pdf.write_bytes(b"<html><body>not a pdf</body></html>")

    item = {
        "name": "Official Cybersecurity Framework",
        "country_code": "UY",
        "entry_type": "standard",
        "mandatory": "recommended",
        "official_url": "https://www.gub.uy/source",
        "artifact_url": "https://www.gub.uy/file.pdf",
        "evidence_note": "official evidence",
        "local_file": str(local_pdf),
    }

    monkeypatch.setattr(
        importer.ComplianceRepository,
        "find_existing",
        lambda name, country_code: {
            "id": "comp-1",
            "name": name,
            "country_code": country_code,
        },
    )

    class _UnexpectedIngest:
        def ingest_uploaded_source(self, *args, **kwargs):
            raise AssertionError("invalid local PDF must be rejected before ingest")

        def ingest_manual_source(self, *args, **kwargs):
            raise AssertionError("local_file should avoid server-side fetching")

    monkeypatch.setattr(importer, "OfficialSourceIngestService", lambda: _UnexpectedIngest())

    try:
        importer.process_item(item, parse_docs=False, generate_spec=False)
    except ValueError as exc:
        assert "不是有效 PDF" in str(exc)
    else:
        raise AssertionError("invalid PDF local_file should fail")


def test_curated_import_verifies_official_artifact_even_when_parse_fails(tmp_path, monkeypatch):
    local_pdf = tmp_path / "scanned.pdf"
    local_pdf.write_bytes(b"%PDF-1.4\nscanned")

    item = {
        "name": "Official Scanned Cyber Law",
        "country_code": "NG",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "official_url": "https://cert.gov.ng/resources",
        "artifact_url": "https://cert.gov.ng/law.pdf",
        "evidence_note": "official evidence",
        "local_file": str(local_pdf),
    }

    monkeypatch.setattr(
        importer.ComplianceRepository,
        "find_existing",
        lambda name, country_code: {
            "id": "comp-1",
            "name": name,
            "country_code": country_code,
        },
    )

    class _FakeIngest:
        def ingest_uploaded_source(self, *args, **kwargs):
            return {
                "doc_id": "doc-1",
                "cos_url": "cos://scanned.pdf",
                "sha256": "abc",
                "file_type": "pdf",
            }

    captured = {}

    class _FakeReview:
        def register_manual_source(self, *args, **kwargs):
            captured["review_registered"] = True
            return {
                "canonical_requirement_id": "canon-1",
                "review_case_id": "review-1",
            }

    class _FailingParseService:
        def parse_document(self, *args, **kwargs):
            return {"success": False, "error": "OCR failed"}

    class _UnexpectedIndexService:
        def index_document(self, *args, **kwargs):
            raise AssertionError("parse failure should skip indexing")

    class _FakeDocRepository:
        @staticmethod
        def set_index_failed(doc_id, error):
            captured["index_failed"] = (doc_id, error)

    monkeypatch.setattr(importer, "OfficialSourceIngestService", lambda: _FakeIngest())
    monkeypatch.setattr(importer, "AuthenticityReviewService", lambda: _FakeReview())
    monkeypatch.setattr(importer, "DocumentParseService", lambda: _FailingParseService())
    monkeypatch.setattr(importer, "DocumentIndexService", lambda: _UnexpectedIndexService())
    monkeypatch.setattr(importer, "DocRepository", _FakeDocRepository)

    result = importer.process_item(item, parse_docs=True, generate_spec=False)

    assert captured["review_registered"] is True
    assert captured["index_failed"] == ("doc-1", "parse failed; index skipped")
    assert result["canonical_requirement_id"] == "canon-1"
    assert result["parse_success"] is False
    assert result["parse_error"] == "OCR failed"
    assert result["index_success"] is False
