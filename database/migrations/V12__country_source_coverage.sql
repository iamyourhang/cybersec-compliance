-- V12__country_source_coverage.sql
-- 国家/地区官方源覆盖矩阵：用于逐国推进“是否已找过、是否有官方源、是否有 verified 数据”。

CREATE TABLE IF NOT EXISTS country_source_coverage (
    country_code            VARCHAR(10) PRIMARY KEY REFERENCES countries(code) ON UPDATE CASCADE,
    coverage_status         VARCHAR(40) NOT NULL DEFAULT 'needs_source_research',
    official_source_count   INTEGER NOT NULL DEFAULT 0,
    source_record_count     INTEGER NOT NULL DEFAULT 0,
    verified_record_count   INTEGER NOT NULL DEFAULT 0,
    suspicious_record_count INTEGER NOT NULL DEFAULT 0,
    quarantined_record_count INTEGER NOT NULL DEFAULT 0,
    review_note             TEXT,
    next_action             TEXT,
    last_checked_at         TIMESTAMPTZ,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_country_source_coverage_status
    ON country_source_coverage(coverage_status, updated_at DESC);
