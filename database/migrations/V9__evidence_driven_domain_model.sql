-- V9__evidence_driven_domain_model.sql
-- 官方证据驱动重构：source_records / source_artifacts / canonical_requirements /
-- review_cases / review_events / compliance_index

CREATE TABLE IF NOT EXISTS source_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    official_source_id  UUID REFERENCES official_sources(id) ON DELETE SET NULL,
    compliance_id       UUID REFERENCES compliance_knowledge(id) ON DELETE SET NULL,
    country_code        VARCHAR(10) NOT NULL,
    title               TEXT NOT NULL,
    entry_type          VARCHAR(30) NOT NULL,
    discovery_method    VARCHAR(50) NOT NULL DEFAULT 'official_source',
    source_url          TEXT,
    artifact_url        TEXT,
    published_date      DATE,
    source_status       VARCHAR(20) NOT NULL DEFAULT 'candidate',
    source_payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_records_country_status
    ON source_records(country_code, source_status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_source_records_country_title_source
    ON source_records(country_code, title, COALESCE(source_url, ''));

CREATE TABLE IF NOT EXISTS source_artifacts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id    UUID REFERENCES source_records(id) ON DELETE CASCADE,
    compliance_id       UUID REFERENCES compliance_knowledge(id) ON DELETE SET NULL,
    document_id         UUID REFERENCES regulation_documents(id) ON DELETE SET NULL,
    official_url        TEXT,
    artifact_url        TEXT,
    artifact_type       VARCHAR(50),
    artifact_sha256     VARCHAR(128),
    download_status     VARCHAR(20) NOT NULL DEFAULT 'pending',
    download_error      TEXT,
    downloaded_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_artifacts_status
    ON source_artifacts(download_status, downloaded_at DESC);

CREATE TABLE IF NOT EXISTS canonical_requirements (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    compliance_id       UUID UNIQUE REFERENCES compliance_knowledge(id) ON DELETE SET NULL,
    source_record_id    UUID REFERENCES source_records(id) ON DELETE SET NULL,
    source_artifact_id  UUID REFERENCES source_artifacts(id) ON DELETE SET NULL,
    document_id         UUID REFERENCES regulation_documents(id) ON DELETE SET NULL,
    country_code        VARCHAR(10) NOT NULL,
    name                TEXT NOT NULL,
    entry_type          VARCHAR(30) NOT NULL,
    mandatory           VARCHAR(20),
    issuing_body        TEXT,
    official_url        TEXT,
    verification_status VARCHAR(20) NOT NULL DEFAULT 'candidate',
    requirement_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_canonical_requirements_status
    ON canonical_requirements(verification_status, country_code, updated_at DESC);

CREATE TABLE IF NOT EXISTS review_cases (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    compliance_id           UUID UNIQUE REFERENCES compliance_knowledge(id) ON DELETE CASCADE,
    source_record_id        UUID REFERENCES source_records(id) ON DELETE SET NULL,
    canonical_requirement_id UUID REFERENCES canonical_requirements(id) ON DELETE SET NULL,
    current_status          VARCHAR(20) NOT NULL DEFAULT 'candidate',
    risk_score              INTEGER NOT NULL DEFAULT 0,
    reasons                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_note           TEXT,
    source_download_status  VARCHAR(20),
    source_download_error   TEXT,
    checked_at              TIMESTAMPTZ,
    checked_by              VARCHAR(120),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_cases_status
    ON review_cases(current_status, updated_at DESC);

CREATE TABLE IF NOT EXISTS review_events (
    id                  BIGSERIAL PRIMARY KEY,
    review_case_id      UUID NOT NULL REFERENCES review_cases(id) ON DELETE CASCADE,
    compliance_id       UUID REFERENCES compliance_knowledge(id) ON DELETE SET NULL,
    event_type          VARCHAR(40) NOT NULL,
    from_status         VARCHAR(20),
    to_status           VARCHAR(20),
    event_payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_by          VARCHAR(120),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_events_case_created
    ON review_events(review_case_id, created_at DESC);

CREATE TABLE IF NOT EXISTS compliance_index (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    compliance_id           UUID UNIQUE REFERENCES compliance_knowledge(id) ON DELETE CASCADE,
    canonical_requirement_id UUID REFERENCES canonical_requirements(id) ON DELETE SET NULL,
    review_case_id          UUID REFERENCES review_cases(id) ON DELETE SET NULL,
    source_record_id        UUID REFERENCES source_records(id) ON DELETE SET NULL,
    source_artifact_id      UUID REFERENCES source_artifacts(id) ON DELETE SET NULL,
    document_id             UUID REFERENCES regulation_documents(id) ON DELETE SET NULL,
    country_code            VARCHAR(10) NOT NULL,
    name                    TEXT NOT NULL,
    entry_type              VARCHAR(30) NOT NULL,
    mandatory               VARCHAR(20),
    status                  VARCHAR(20),
    issuing_body            TEXT,
    official_url            TEXT,
    authenticity_status     VARCHAR(20) NOT NULL DEFAULT 'candidate',
    authenticity_risk_score INTEGER NOT NULL DEFAULT 0,
    applicable_products     TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    effective_date          DATE,
    published_date          DATE,
    summary                 TEXT,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_compliance_index_country_status
    ON compliance_index(country_code, authenticity_status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_compliance_index_products
    ON compliance_index USING GIN(applicable_products);

INSERT INTO review_cases (
    compliance_id,
    current_status,
    risk_score,
    reasons,
    evidence_note,
    source_download_status,
    source_download_error,
    checked_at,
    checked_by
)
SELECT
    ck.id,
    COALESCE(ck.authenticity_status, 'candidate'),
    COALESCE(ck.authenticity_risk_score, 0),
    COALESCE(ck.authenticity_reasons, '[]'::jsonb),
    ck.authenticity_evidence,
    ck.source_download_status,
    ck.source_download_error,
    ck.authenticity_checked_at,
    ck.authenticity_checked_by
FROM compliance_knowledge ck
WHERE NOT EXISTS (
    SELECT 1 FROM review_cases rc WHERE rc.compliance_id = ck.id
);

INSERT INTO source_artifacts (
    compliance_id,
    document_id,
    official_url,
    artifact_url,
    artifact_type,
    artifact_sha256,
    download_status,
    download_error,
    downloaded_at
)
SELECT
    ck.id,
    ck.source_document_id,
    ck.official_url,
    ck.source_artifact_url,
    ck.source_artifact_type,
    ck.source_artifact_sha256,
    COALESCE(ck.source_download_status, 'pending'),
    ck.source_download_error,
    ck.source_downloaded_at
FROM compliance_knowledge ck
WHERE ck.official_url IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM source_artifacts sa
      WHERE sa.compliance_id = ck.id
  );

INSERT INTO canonical_requirements (
    compliance_id,
    document_id,
    country_code,
    name,
    entry_type,
    mandatory,
    issuing_body,
    official_url,
    verification_status,
    requirement_payload
)
SELECT
    ck.id,
    ck.source_document_id,
    ck.country_code,
    ck.name,
    ck.entry_type,
    ck.mandatory,
    ck.issuing_body,
    ck.official_url,
    CASE
        WHEN COALESCE(ck.authenticity_status, 'candidate') = 'verified' THEN 'verified'
        WHEN COALESCE(ck.authenticity_status, 'candidate') = 'quarantined' THEN 'quarantined'
        ELSE 'candidate'
    END,
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
WHERE NOT EXISTS (
    SELECT 1 FROM canonical_requirements cr WHERE cr.compliance_id = ck.id
);

UPDATE canonical_requirements cr
SET source_artifact_id = sa.id
FROM source_artifacts sa
WHERE sa.compliance_id = cr.compliance_id
  AND cr.source_artifact_id IS NULL;

INSERT INTO compliance_index (
    compliance_id,
    canonical_requirement_id,
    review_case_id,
    source_artifact_id,
    document_id,
    country_code,
    name,
    entry_type,
    mandatory,
    status,
    issuing_body,
    official_url,
    authenticity_status,
    authenticity_risk_score,
    applicable_products,
    effective_date,
    published_date,
    summary
)
SELECT
    ck.id,
    cr.id,
    rc.id,
    sa.id,
    ck.source_document_id,
    ck.country_code,
    ck.name,
    ck.entry_type,
    ck.mandatory,
    ck.status,
    ck.issuing_body,
    ck.official_url,
    COALESCE(ck.authenticity_status, 'candidate'),
    COALESCE(ck.authenticity_risk_score, 0),
    COALESCE(ck.applicable_products, ARRAY[]::TEXT[]),
    ck.effective_date,
    ck.published_date,
    COALESCE(ck.scope_description, ck.remarks)
FROM compliance_knowledge ck
LEFT JOIN canonical_requirements cr ON cr.compliance_id = ck.id
LEFT JOIN review_cases rc ON rc.compliance_id = ck.id
LEFT JOIN source_artifacts sa ON sa.compliance_id = ck.id
WHERE ck.status = 'active'
  AND NOT EXISTS (
      SELECT 1 FROM compliance_index ci WHERE ci.compliance_id = ck.id
  );
