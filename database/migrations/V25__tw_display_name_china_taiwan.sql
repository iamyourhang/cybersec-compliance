UPDATE countries
SET name_zh = '中国台湾',
    name_en = 'Taiwan, China',
    jurisdiction_type = COALESCE(jurisdiction_type, 'special_region'),
    updated_at = NOW()
WHERE code = 'TW';
