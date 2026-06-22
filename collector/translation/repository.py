"""Persistence helpers for additive Chinese translations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from database.connection import get_cursor

from collector.translation.service import TranslationJob


def upsert_translation_jobs(
    jobs: Iterable[TranslationJob],
    target_language: str = "zh-CN",
) -> int:
    """Create pending translation rows without overwriting completed work."""
    count = 0
    with get_cursor() as cur:
        for job in jobs:
            cur.execute(
                """
                INSERT INTO content_translations (
                    entity_type,
                    entity_id,
                    field_name,
                    target_language,
                    source_text_hash,
                    source_text,
                    translation_status,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
                ON CONFLICT (
                    entity_type,
                    entity_id,
                    field_name,
                    target_language,
                    source_text_hash
                )
                DO UPDATE SET
                    source_text = EXCLUDED.source_text,
                    updated_at = NOW(),
                    translation_status = CASE
                        WHEN content_translations.translation_status = 'failed'
                        THEN 'pending'
                        ELSE content_translations.translation_status
                    END,
                    error = CASE
                        WHEN content_translations.translation_status = 'failed'
                        THEN NULL
                        ELSE content_translations.error
                    END
                """,
                (
                    job.entity_type,
                    job.entity_id,
                    job.field_name,
                    target_language,
                    job.source_text_hash,
                    job.source_text,
                ),
            )
            count += 1
    return count


def list_completed_translations_by_hash(
    source_text_hashes: Iterable[str],
    target_language: str = "zh-CN",
) -> dict[str, str]:
    hashes = sorted(set(source_text_hashes))
    if not hashes:
        return {}
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (source_text_hash)
                   source_text_hash,
                   translated_text
            FROM content_translations
            WHERE target_language = %s
              AND translation_status = 'completed'
              AND translated_text IS NOT NULL
              AND source_text_hash = ANY(%s)
            ORDER BY source_text_hash, translated_at DESC NULLS LAST, updated_at DESC
            """,
            (target_language, hashes),
        )
        return {str(row["source_text_hash"]): row["translated_text"] for row in cur.fetchall()}


def store_reused_translations(
    jobs: Iterable[TranslationJob],
    completed_by_hash: Mapping[str, str],
    target_language: str = "zh-CN",
    provider_name: str = "hash_reuse",
    model: str = "hash_reuse",
) -> int:
    count = 0
    for job in jobs:
        translated_text = completed_by_hash.get(job.source_text_hash)
        if translated_text:
            store_completed_translation(
                job,
                translated_text,
                target_language=target_language,
                provider_name=provider_name,
                model=model,
            )
            count += 1
    return count


def store_completed_translation(
    job: TranslationJob,
    translated_text: str,
    target_language: str = "zh-CN",
    provider_name: str | None = None,
    model: str | None = None,
) -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO content_translations (
                entity_type,
                entity_id,
                field_name,
                target_language,
                source_text_hash,
                source_text,
                translated_text,
                translation_status,
                provider_name,
                model,
                translated_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed', %s, %s, NOW(), NOW())
            ON CONFLICT (
                entity_type,
                entity_id,
                field_name,
                target_language,
                source_text_hash
            )
            DO UPDATE SET
                source_text = EXCLUDED.source_text,
                translated_text = EXCLUDED.translated_text,
                translation_status = 'completed',
                provider_name = EXCLUDED.provider_name,
                model = EXCLUDED.model,
                error = NULL,
                translated_at = NOW(),
                updated_at = NOW()
            """,
            (
                job.entity_type,
                job.entity_id,
                job.field_name,
                target_language,
                job.source_text_hash,
                job.source_text,
                translated_text,
                provider_name,
                model,
            ),
        )


def store_failed_translation(
    job: TranslationJob,
    error: str,
    target_language: str = "zh-CN",
) -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO content_translations (
                entity_type,
                entity_id,
                field_name,
                target_language,
                source_text_hash,
                source_text,
                translation_status,
                error,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'failed', %s, NOW())
            ON CONFLICT (
                entity_type,
                entity_id,
                field_name,
                target_language,
                source_text_hash
            )
            DO UPDATE SET
                source_text = EXCLUDED.source_text,
                translation_status = 'failed',
                error = EXCLUDED.error,
                updated_at = NOW()
            """,
            (
                job.entity_type,
                job.entity_id,
                job.field_name,
                target_language,
                job.source_text_hash,
                job.source_text,
                error[:2000],
            ),
        )


def list_translations_for_entities(
    entity_type: str,
    entity_ids: Iterable[str],
    target_language: str = "zh-CN",
) -> dict[tuple[str, str], str]:
    ids = [str(entity_id) for entity_id in entity_ids if entity_id]
    if not ids:
        return {}
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (entity_id, field_name)
                   entity_id,
                   field_name,
                   translated_text
            FROM content_translations
            WHERE entity_type = %s
              AND target_language = %s
              AND translation_status = 'completed'
              AND translated_text IS NOT NULL
              AND entity_id = ANY(%s)
            ORDER BY entity_id, field_name, translated_at DESC NULLS LAST, updated_at DESC
            """,
            (entity_type, target_language, ids),
        )
        return {
            (str(row["entity_id"]), str(row["field_name"])): row["translated_text"]
            for row in cur.fetchall()
        }

