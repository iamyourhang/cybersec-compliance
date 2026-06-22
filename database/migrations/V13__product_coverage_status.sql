-- V13__product_coverage_status.sql
-- 将国家覆盖拆分为“是否有官方源”和“是否有产品级网络安全法规/认证/标准”两个维度。

ALTER TABLE country_source_coverage
    ADD COLUMN IF NOT EXISTS product_coverage_status VARCHAR(60) NOT NULL DEFAULT 'pending_source_research',
    ADD COLUMN IF NOT EXISTS product_verified_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS general_verified_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_country_source_coverage_product_status
    ON country_source_coverage(product_coverage_status, updated_at DESC);
