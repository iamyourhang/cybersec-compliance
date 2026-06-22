CREATE TABLE IF NOT EXISTS agent_cases (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question                TEXT NOT NULL,
    country_code            VARCHAR(10),
    product_code            VARCHAR(80),
    document_id             VARCHAR(80),
    intent                  VARCHAR(60) NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'open',
    failure_reason          TEXT,
    evidence_snapshot       JSONB NOT NULL DEFAULT '{}'::jsonb,
    tool_trace              JSONB NOT NULL DEFAULT '[]'::jsonb,
    suggested_actions       TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    source                  VARCHAR(60) NOT NULL DEFAULT 'agent',
    created_by              VARCHAR(120) NOT NULL DEFAULT 'agent',
    handled_by              VARCHAR(120),
    handler_note            TEXT,
    linked_source_record_id VARCHAR(80),
    linked_review_case_id   VARCHAR(80),
    linked_document_id      VARCHAR(80),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_cases_status
    ON agent_cases(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_cases_country_intent
    ON agent_cases(country_code, intent, created_at DESC);
