-- Align legacy upcoming view with the evidence-driven read model.
-- Flybook/legacy callers may still read v_upcoming_effective, so the view
-- must exclude candidate/suspicious/quarantined records.

DROP VIEW IF EXISTS v_upcoming_effective;

CREATE VIEW v_upcoming_effective AS
SELECT
    ci.compliance_id AS id,
    ci.name,
    ci.entry_type,
    ci.country_code,
    c.name_zh AS country_name,
    c.priority,
    ci.effective_date,
    ci.effective_date - CURRENT_DATE AS days_until_effective,
    ci.mandatory,
    ci.applicable_products
FROM compliance_index ci
JOIN countries c ON ci.country_code = c.code
WHERE ci.status = 'active'
  AND ci.authenticity_status = 'verified'
  AND ci.effective_date IS NOT NULL
  AND ci.effective_date >= CURRENT_DATE
  AND ci.effective_date <= CURRENT_DATE + INTERVAL '360 days'
ORDER BY ci.effective_date, c.priority, ci.name;
