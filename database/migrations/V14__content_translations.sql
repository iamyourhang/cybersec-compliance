-- V14__content_translations.sql
-- 通用中文译文层：保留原文字段，只追加中文译文。

CREATE TABLE IF NOT EXISTS content_translations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type         VARCHAR(80) NOT NULL,
    entity_id           TEXT NOT NULL,
    field_name          TEXT NOT NULL,
    source_language     VARCHAR(20),
    target_language     VARCHAR(20) NOT NULL DEFAULT 'zh-CN',
    source_text_hash    VARCHAR(64) NOT NULL,
    source_text         TEXT NOT NULL,
    translated_text     TEXT,
    translation_status  VARCHAR(20) NOT NULL DEFAULT 'pending',
    provider_name       VARCHAR(120),
    model               VARCHAR(120),
    error               TEXT,
    translated_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(entity_type, entity_id, field_name, target_language, source_text_hash)
);

CREATE INDEX IF NOT EXISTS idx_content_translations_entity
    ON content_translations(entity_type, entity_id, target_language);

CREATE INDEX IF NOT EXISTS idx_content_translations_status
    ON content_translations(translation_status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_content_translations_hash
    ON content_translations(source_text_hash, target_language);
