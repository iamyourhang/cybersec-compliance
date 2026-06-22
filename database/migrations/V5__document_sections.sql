-- ============================================================
-- V5__document_sections.sql
-- 法规原文结构层：章节/条款/附件
-- ============================================================

CREATE TABLE IF NOT EXISTS regulation_document_sections (
    id              BIGSERIAL PRIMARY KEY,
    document_id     UUID NOT NULL REFERENCES regulation_documents(id) ON DELETE CASCADE,
    section_index   INTEGER NOT NULL,
    section_type    VARCHAR(30) NOT NULL,
    section_ref     VARCHAR(200) NOT NULL,
    title           TEXT,
    section_path    TEXT,
    page_from       INTEGER NOT NULL,
    page_to         INTEGER NOT NULL,
    content         TEXT NOT NULL,
    content_tsv     TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, '') || ' ' || coalesce(title, '') || ' ' || coalesce(section_ref, ''))) STORED,
    country_code    VARCHAR(10) NOT NULL REFERENCES countries(code) ON UPDATE CASCADE,
    compliance_id   UUID REFERENCES compliance_knowledge(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, section_index)
);

CREATE INDEX IF NOT EXISTS idx_rds_document_section
    ON regulation_document_sections(document_id, section_index);
CREATE INDEX IF NOT EXISTS idx_rds_ref
    ON regulation_document_sections(section_ref);
CREATE INDEX IF NOT EXISTS idx_rds_title_tsv
    ON regulation_document_sections USING GIN(content_tsv);
