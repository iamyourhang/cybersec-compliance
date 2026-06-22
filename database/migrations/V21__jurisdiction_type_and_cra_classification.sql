-- V21__jurisdiction_type_and_cra_classification.sql
-- Countries table is also used for non-country regulatory markets such as EU.

ALTER TABLE countries
    ADD COLUMN IF NOT EXISTS jurisdiction_type VARCHAR(40) NOT NULL DEFAULT 'country';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_countries_jurisdiction_type'
    ) THEN
        ALTER TABLE countries
            ADD CONSTRAINT ck_countries_jurisdiction_type
            CHECK (jurisdiction_type IN ('country', 'regional_bloc', 'special_region', 'territory'));
    END IF;
END $$;

UPDATE countries
SET jurisdiction_type = CASE
    WHEN code = 'EU' THEN 'regional_bloc'
    WHEN code IN ('TW', 'HK', 'MO') THEN 'special_region'
    ELSE 'country'
END;

UPDATE compliance_index
SET regime_category = 'product_regime'
WHERE authenticity_status = 'verified'
  AND lower(coalesce(name, '') || ' ' || coalesce(summary, '')) ~
      'cyber resilience act|products with digital elements|horizontal cybersecurity requirements';
