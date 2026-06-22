-- ============================================================
-- V4__llm_channels.sql
-- LLM 通道池与事件日志
-- ============================================================

CREATE TABLE IF NOT EXISTS llm_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    provider_type VARCHAR(50) NOT NULL,
    base_url TEXT NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    model VARCHAR(200) NOT NULL,
    priority INT NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    supports_web_search BOOLEAN NOT NULL DEFAULT FALSE,
    quota_exhausted BOOLEAN NOT NULL DEFAULT FALSE,
    manual_pause BOOLEAN NOT NULL DEFAULT FALSE,
    last_error TEXT,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_channels_priority
    ON llm_channels (enabled, manual_pause, quota_exhausted, priority);

CREATE TABLE IF NOT EXISTS llm_channel_events (
    id BIGSERIAL PRIMARY KEY,
    channel_id UUID NOT NULL REFERENCES llm_channels(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    message TEXT,
    raw_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_channel_events_channel_created
    ON llm_channel_events (channel_id, created_at DESC);
