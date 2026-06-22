-- V7__official_sources.sql
-- 官方源白名单与同步历史

CREATE TABLE IF NOT EXISTS official_sources (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    country_code        VARCHAR(10) NOT NULL REFERENCES countries(code) ON UPDATE CASCADE,
    name                VARCHAR(200) NOT NULL,
    base_url            TEXT NOT NULL,
    list_url            TEXT NOT NULL,
    source_type         VARCHAR(50) NOT NULL,
    allowed_domains     TEXT[] NOT NULL DEFAULT '{}',
    entry_type_scope    TEXT[] NOT NULL DEFAULT '{}',
    poll_interval_hours INTEGER NOT NULL DEFAULT 24,
    priority            INTEGER NOT NULL DEFAULT 100,
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    parser_config       JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_checked_at     TIMESTAMPTZ,
    last_success_at     TIMESTAMPTZ,
    last_error          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(country_code, name)
);

CREATE INDEX IF NOT EXISTS idx_official_sources_country_enabled
    ON official_sources(country_code, enabled, priority);

CREATE INDEX IF NOT EXISTS idx_official_sources_type
    ON official_sources(source_type);

CREATE TABLE IF NOT EXISTS official_source_history (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           UUID NOT NULL REFERENCES official_sources(id) ON DELETE CASCADE,
    status              VARCHAR(20) NOT NULL,
    discovered_count    INTEGER NOT NULL DEFAULT 0,
    candidate_count     INTEGER NOT NULL DEFAULT 0,
    artifact_count      INTEGER NOT NULL DEFAULT 0,
    error               TEXT,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_official_source_history_source_started
    ON official_source_history(source_id, started_at DESC);

INSERT INTO official_sources
    (country_code, name, base_url, list_url, source_type, allowed_domains, entry_type_scope, priority, parser_config)
VALUES
    (
        'EU',
        'EUR-Lex',
        'https://eur-lex.europa.eu',
        'https://eur-lex.europa.eu',
        'html_list',
        ARRAY['eur-lex.europa.eu'],
        ARRAY['regulation','standard'],
        1,
        '{"url_patterns":["/eli/","/legal-content/EN/TXT/PDF/"]}'::jsonb
    ),
    (
        'GB',
        'legislation.gov.uk',
        'https://www.legislation.gov.uk',
        'https://www.legislation.gov.uk',
        'html_list',
        ARRAY['legislation.gov.uk'],
        ARRAY['regulation'],
        2,
        '{"url_patterns":["/ukpga/","/uksi/","/ukia/"]}'::jsonb
    ),
    (
        'US',
        'NIST CSRC',
        'https://csrc.nist.gov',
        'https://csrc.nist.gov/Publications',
        'html_list',
        ARRAY['csrc.nist.gov','nist.gov','nvlpubs.nist.gov'],
        ARRAY['standard'],
        3,
        '{"url_patterns":["/pubs/","/Publications","nvlpubs.nist.gov"]}'::jsonb
    ),
    (
        'US',
        'FCC',
        'https://www.fcc.gov',
        'https://www.fcc.gov',
        'pdf_index',
        ARRAY['fcc.gov','docs.fcc.gov'],
        ARRAY['certification','regulation'],
        4,
        '{"url_patterns":["Cyber Trust Mark","docs.fcc.gov/public/attachments/"]}'::jsonb
    ),
    (
        'JP',
        'METI',
        'https://www.meti.go.jp',
        'https://www.meti.go.jp/english/policy/safety_security/cybersecurity/index.html',
        'html_list',
        ARRAY['meti.go.jp'],
        ARRAY['regulation','certification'],
        5,
        '{"url_patterns":["jc-star","cybersecurity","press"]}'::jsonb
    ),
    (
        'JP',
        'IPA',
        'https://www.ipa.go.jp',
        'https://www.ipa.go.jp/en/security/jc-star/kitei.html',
        'html_list',
        ARRAY['ipa.go.jp'],
        ARRAY['certification','standard'],
        6,
        '{"url_patterns":["jc-star","security"]}'::jsonb
    ),
    (
        'SG',
        'CSA Singapore',
        'https://www.csa.gov.sg',
        'https://www.csa.gov.sg/our-programmes/certification-and-labelling-schemes',
        'html_list',
        ARRAY['csa.gov.sg'],
        ARRAY['certification','regulation'],
        7,
        '{"url_patterns":["cybersecurity-labelling-scheme","certification-and-labelling-schemes","updates"]}'::jsonb
    )
ON CONFLICT (country_code, name) DO NOTHING;
