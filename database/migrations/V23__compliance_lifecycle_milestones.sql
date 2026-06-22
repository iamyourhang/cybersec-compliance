-- V23__compliance_lifecycle_milestones.sql
-- A single effective_date is not enough for staged regulations such as the EU
-- Cyber Resilience Act. Store official lifecycle milestones separately and keep
-- compliance_index.effective_date as the primary/full application date.

CREATE TABLE IF NOT EXISTS compliance_lifecycle_milestones (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    compliance_id       UUID NOT NULL REFERENCES compliance_knowledge(id) ON DELETE CASCADE,
    milestone_key       VARCHAR(80) NOT NULL,
    milestone_type      VARCHAR(40) NOT NULL,
    milestone_label_zh  TEXT NOT NULL,
    milestone_label_en  TEXT,
    milestone_date      DATE NOT NULL,
    obligation_scope    TEXT,
    legal_basis         TEXT,
    source_note         TEXT,
    alertable           BOOLEAN NOT NULL DEFAULT TRUE,
    priority            INTEGER NOT NULL DEFAULT 100,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (compliance_id, milestone_key)
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_milestones_date
    ON compliance_lifecycle_milestones(milestone_date, alertable);

CREATE INDEX IF NOT EXISTS idx_lifecycle_milestones_compliance
    ON compliance_lifecycle_milestones(compliance_id, priority);

WITH cra AS (
    SELECT ci.compliance_id
    FROM compliance_index ci
    WHERE ci.authenticity_status = 'verified'
      AND (
        ci.official_url ILIKE '%eur-lex.europa.eu/eli/reg/2024/2847%'
        OR ci.name ILIKE '%Cyber Resilience Act%'
        OR ci.name ILIKE '%2024/2847%'
      )
    ORDER BY ci.updated_at DESC
    LIMIT 1
)
INSERT INTO compliance_lifecycle_milestones (
    compliance_id,
    milestone_key,
    milestone_type,
    milestone_label_zh,
    milestone_label_en,
    milestone_date,
    obligation_scope,
    legal_basis,
    source_note,
    alertable,
    priority
)
SELECT
    cra.compliance_id,
    values_row.milestone_key,
    values_row.milestone_type,
    values_row.milestone_label_zh,
    values_row.milestone_label_en,
    values_row.milestone_date::date,
    values_row.obligation_scope,
    values_row.legal_basis,
    values_row.source_note,
    values_row.alertable,
    values_row.priority
FROM cra
CROSS JOIN (
    VALUES
        (
            'entry_into_force',
            'entry_into_force',
            '法规已生效 / entered into force',
            'Entered into force',
            '2024-12-10',
            'Regulation (EU) 2024/2847 became EU law.',
            'Article 71(1)',
            'EUR-Lex official text: Regulation (EU) 2024/2847, Article 71.',
            FALSE,
            10
        ),
        (
            'notified_body_rules_apply',
            'application',
            '合格评定机构通知规则开始适用',
            'Rules on notification of conformity assessment bodies apply',
            '2026-06-11',
            'Chapter IV (Articles 35 to 51) on notification of conformity assessment bodies.',
            'Article 71(2); Chapter IV (Articles 35 to 51)',
            'EUR-Lex official text: Regulation (EU) 2024/2847, Article 71.',
            TRUE,
            20
        ),
        (
            'reporting_obligations_apply',
            'obligation',
            '漏洞与严重事件报告义务开始适用',
            'Reporting obligations for actively exploited vulnerabilities and severe incidents apply',
            '2026-09-11',
            'Article 14 reporting obligations for actively exploited vulnerabilities and severe incidents.',
            'Article 71(2); Article 14',
            'EUR-Lex official text: Regulation (EU) 2024/2847, Article 71.',
            TRUE,
            30
        ),
        (
            'full_application',
            'application',
            '主要义务 / 全面适用',
            'Full application of the main obligations',
            '2027-12-11',
            'The Regulation generally applies from this date.',
            'Article 71(2)',
            'EUR-Lex official text: Regulation (EU) 2024/2847, Article 71.',
            TRUE,
            40
        )
) AS values_row (
    milestone_key,
    milestone_type,
    milestone_label_zh,
    milestone_label_en,
    milestone_date,
    obligation_scope,
    legal_basis,
    source_note,
    alertable,
    priority
)
ON CONFLICT (compliance_id, milestone_key) DO UPDATE SET
    milestone_type = EXCLUDED.milestone_type,
    milestone_label_zh = EXCLUDED.milestone_label_zh,
    milestone_label_en = EXCLUDED.milestone_label_en,
    milestone_date = EXCLUDED.milestone_date,
    obligation_scope = EXCLUDED.obligation_scope,
    legal_basis = EXCLUDED.legal_basis,
    source_note = EXCLUDED.source_note,
    alertable = EXCLUDED.alertable,
    priority = EXCLUDED.priority,
    updated_at = NOW();

UPDATE compliance_index
SET effective_date = '2027-12-11'::date,
    updated_at = NOW()
WHERE authenticity_status = 'verified'
  AND (
    official_url ILIKE '%eur-lex.europa.eu/eli/reg/2024/2847%'
    OR name ILIKE '%Cyber Resilience Act%'
    OR name ILIKE '%2024/2847%'
  );
