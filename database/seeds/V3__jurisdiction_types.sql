-- Jurisdiction metadata. Runs after the base country catalog seed.

UPDATE countries
SET jurisdiction_type = CASE
    WHEN code = 'EU' THEN 'regional_bloc'
    WHEN code IN ('TW', 'HK', 'MO') THEN 'special_region'
    ELSE 'country'
END;
