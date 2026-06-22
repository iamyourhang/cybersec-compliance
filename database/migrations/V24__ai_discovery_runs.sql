-- V24__ai_discovery_runs.sql
-- 受控 AI Discovery：只记录发现运行和候选统计，不直接产出 verified。

CREATE TABLE IF NOT EXISTS ai_discovery_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at      TIMESTAMPTZ,
    scope            JSONB NOT NULL DEFAULT '{}'::jsonb,
    countries_count  INTEGER NOT NULL DEFAULT 0,
    queries_count    INTEGER NOT NULL DEFAULT 0,
    candidate_count  INTEGER NOT NULL DEFAULT 0,
    accepted_count   INTEGER NOT NULL DEFAULT 0,
    rejected_count   INTEGER NOT NULL DEFAULT 0,
    status           VARCHAR(30) NOT NULL DEFAULT 'running',
    error            TEXT
);

CREATE INDEX IF NOT EXISTS idx_ai_discovery_runs_started
    ON ai_discovery_runs(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_records_ai_discovery
    ON source_records(discovery_method, created_at DESC)
    WHERE discovery_method = 'ai_weekly_discovery';
