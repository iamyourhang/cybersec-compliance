-- ============================================================
-- RAG 文档索引能力
-- 目标：
-- 1. 对齐 regulation_documents 结构
-- 2. 新增 regulation_document_chunks 作为唯一检索表
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE IF NOT EXISTS regulation_documents (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    compliance_id       UUID REFERENCES compliance_knowledge(id) ON DELETE SET NULL,
    name                VARCHAR(500) NOT NULL,
    country_code        VARCHAR(10) NOT NULL REFERENCES countries(code) ON UPDATE CASCADE,
    file_name           VARCHAR(500) NOT NULL,
    cos_key             TEXT NOT NULL,
    cos_url             TEXT,
    file_size           BIGINT,
    file_type           VARCHAR(20) NOT NULL DEFAULT 'pdf',
    parse_status        VARCHAR(20) NOT NULL DEFAULT 'pending',
    parse_result        JSONB,
    parse_error         TEXT,
    parsed_at           TIMESTAMPTZ,
    uploaded_by         VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    spec_cos_url        TEXT,
    spec_cos_key        TEXT,
    spec_generated_at   TIMESTAMPTZ,
    progress            INTEGER NOT NULL DEFAULT 0,
    progress_msg        VARCHAR(200),
    spec_progress       INTEGER NOT NULL DEFAULT 0,
    spec_progress_msg   VARCHAR(200)
);

ALTER TABLE regulation_documents
    ADD COLUMN IF NOT EXISTS index_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS index_error TEXT,
    ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS page_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS chunk_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_rd_country_created
    ON regulation_documents(country_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rd_parse_status
    ON regulation_documents(parse_status);
CREATE INDEX IF NOT EXISTS idx_rd_index_status
    ON regulation_documents(index_status);

CREATE TABLE IF NOT EXISTS regulation_document_chunks (
    id              BIGSERIAL PRIMARY KEY,
    document_id     UUID NOT NULL REFERENCES regulation_documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    page_from       INTEGER NOT NULL,
    page_to         INTEGER NOT NULL,
    section_path    TEXT,
    clause_ref      VARCHAR(120),
    content         TEXT NOT NULL,
    content_tsv     TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED,
    embedding       vector(1536),
    country_code    VARCHAR(10) NOT NULL REFERENCES countries(code) ON UPDATE CASCADE,
    compliance_id   UUID REFERENCES compliance_knowledge(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_rdc_document_chunk
    ON regulation_document_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_rdc_country_created
    ON regulation_document_chunks(country_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rdc_clause_ref
    ON regulation_document_chunks(clause_ref);
CREATE INDEX IF NOT EXISTS idx_rdc_content_tsv
    ON regulation_document_chunks USING GIN(content_tsv);
CREATE INDEX IF NOT EXISTS idx_rdc_embedding
    ON regulation_document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
