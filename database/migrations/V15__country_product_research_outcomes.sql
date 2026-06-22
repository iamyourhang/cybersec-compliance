-- V15__country_product_research_outcomes.sql
-- 产品级网络安全制度研究结论。
--
-- 一个国家可以同时存在 verified 通用网络安全法规，以及“未发现独立产品级
-- 网络安全认证/准入/标签制度”的研究结论。该表用于保存这个结论，避免
-- country_source_coverage 每次刷新时把已研究过的国家重新打回 pending。

CREATE TABLE IF NOT EXISTS country_product_research_outcomes (
    country_code        VARCHAR(10) PRIMARY KEY REFERENCES countries(code) ON UPDATE CASCADE,
    outcome_status      VARCHAR(60) NOT NULL,
    review_note         TEXT NOT NULL,
    evidence_urls       TEXT[] NOT NULL DEFAULT '{}',
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checked_by          VARCHAR(120) NOT NULL DEFAULT 'official-source-research',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_country_product_research_outcome_status CHECK (
        outcome_status IN (
            'no_product_regime_found_verified',
            'product_regime_research_pending',
            'product_regime_candidate_found'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_country_product_research_outcomes_status
    ON country_product_research_outcomes(outcome_status, checked_at DESC);
