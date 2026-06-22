-- V20__remove_cross_regulation_spec_noise.sql
-- Remove specs that clearly cite another regulation family than their source document.

DELETE FROM regulation_spec_requirements
WHERE lower(coalesce(regulation_name, '')) NOT LIKE '%cyber resilience act%'
  AND (
      lower(coalesce(req_id, '')) LIKE '%-cra-%'
      OR lower(coalesce(description_zh, '')) LIKE '% cra %'
      OR lower(coalesce(description_en, '')) LIKE '% cyber resilience act%'
      OR lower(coalesce(regulation_clause, '')) LIKE '%annex i part ii%'
  );
