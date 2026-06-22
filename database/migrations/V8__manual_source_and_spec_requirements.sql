-- V8__manual_source_and_spec_requirements.sql
-- 人工补源 + 规格结构化入库

ALTER TABLE regulation_documents
    ADD COLUMN IF NOT EXISTS spec_requirement_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS regulation_spec_requirements (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id             UUID NOT NULL REFERENCES regulation_documents(id) ON DELETE CASCADE,
    compliance_id           UUID REFERENCES compliance_knowledge(id) ON DELETE SET NULL,
    country_code            VARCHAR(8) NOT NULL,
    regulation_name         VARCHAR(300) NOT NULL,
    req_id                  VARCHAR(80) NOT NULL,
    module_zh               VARCHAR(120),
    module_en               VARCHAR(120),
    title_zh                VARCHAR(200),
    title_en                VARCHAR(200),
    description_zh          TEXT,
    description_en          TEXT,
    applicable_products     TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    mandatory               VARCHAR(20),
    priority                VARCHAR(10),
    regulation_clause       VARCHAR(120),
    verification_method_zh  TEXT,
    verification_method_en  TEXT,
    notes_zh                TEXT,
    notes_en                TEXT,
    source_pages            VARCHAR(120),
    source_chunk_ids        UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, req_id)
);

CREATE INDEX IF NOT EXISTS idx_spec_requirements_document
    ON regulation_spec_requirements(document_id, priority, req_id);

CREATE INDEX IF NOT EXISTS idx_spec_requirements_country
    ON regulation_spec_requirements(country_code, priority);

CREATE INDEX IF NOT EXISTS idx_spec_requirements_products
    ON regulation_spec_requirements USING GIN(applicable_products);

UPDATE official_sources
SET parser_config = COALESCE(parser_config, '{}'::jsonb) || jsonb_build_object(
    'exclude_url_patterns', ARRAY[
        '/feeds/',
        '\\.rss$',
        '\\.json$',
        '\\.xlsx$',
        '/Publications/?$',
        '/publications/?$',
        '/news-events/?$',
        '/events/?$'
    ],
    'exclude_title_patterns', ARRAY[
        'view all',
        'rss',
        'json',
        'xlsx',
        'quarterly',
        'newsletter',
        'catalog'
    ]
)
WHERE name IN ('NIST CSRC', 'FCC', 'IPA');
