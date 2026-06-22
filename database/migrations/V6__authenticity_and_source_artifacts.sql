-- ============================================================
-- V6__authenticity_and_source_artifacts.sql
-- 合规条目真实性状态 + 官方原文工件下载状态
-- ============================================================

ALTER TABLE compliance_knowledge
    ADD COLUMN IF NOT EXISTS authenticity_status VARCHAR(20) NOT NULL DEFAULT 'candidate',
    ADD COLUMN IF NOT EXISTS authenticity_risk_score SMALLINT,
    ADD COLUMN IF NOT EXISTS authenticity_reasons JSONB,
    ADD COLUMN IF NOT EXISTS authenticity_checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS authenticity_checked_by VARCHAR(100),
    ADD COLUMN IF NOT EXISTS authenticity_evidence TEXT,
    ADD COLUMN IF NOT EXISTS source_document_id UUID REFERENCES regulation_documents(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS source_artifact_url TEXT,
    ADD COLUMN IF NOT EXISTS source_artifact_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS source_artifact_sha256 VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_download_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS source_download_error TEXT,
    ADD COLUMN IF NOT EXISTS source_downloaded_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_ck_authenticity_status
    ON compliance_knowledge(authenticity_status);

CREATE INDEX IF NOT EXISTS idx_ck_source_download_status
    ON compliance_knowledge(source_download_status);
