-- V17__verified_pending_review_view.sql
-- 将待审核变更视图切到 verified 读模型，避免后台/脚本继续从旧正式表取数。

DROP VIEW IF EXISTS v_pending_review;

CREATE VIEW v_pending_review AS
SELECT
    cl.id AS log_id,
    cl.record_id,
    ci.name,
    ci.country_code,
    c.name_zh AS country_name,
    cl.change_type,
    cl.changed_fields,
    cl.diff_summary,
    cl.changed_at
FROM change_log cl
JOIN compliance_index ci ON cl.record_id = ci.compliance_id
JOIN countries c ON ci.country_code = c.code
WHERE cl.reviewed = FALSE
  AND ci.status = 'active'
  AND ci.authenticity_status = 'verified'
ORDER BY cl.changed_at DESC;
