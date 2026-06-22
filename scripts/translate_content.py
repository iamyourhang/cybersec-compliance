#!/usr/bin/env python3
"""Translate stored compliance content into Simplified Chinese.

This script is intentionally additive: it writes translations to
content_translations and never mutates source evidence fields.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.providers.channel_router import get_channel_router
from collector.translation.repository import (
    list_completed_translations_by_hash,
    store_completed_translation,
    store_failed_translation,
    store_reused_translations,
    upsert_translation_jobs,
)
from collector.translation.service import TranslationJob, build_translation_jobs, parse_translation_json
from database.connection import get_cursor
from utils.logger import setup_logging

setup_logging(level="INFO")
logger = logging.getLogger("translate_content")


@dataclass(frozen=True)
class TableTranslationConfig:
    entity_type: str
    sql: str
    fields: list[str]


METADATA_TABLES: list[TableTranslationConfig] = [
    TableTranslationConfig(
        entity_type="compliance_index",
        sql="""
            SELECT
                compliance_id::text AS id,
                name,
                issuing_body,
                summary
            FROM compliance_index
            WHERE status = 'active'
            ORDER BY updated_at DESC
        """,
        fields=["name", "issuing_body", "summary"],
    ),
    TableTranslationConfig(
        entity_type="compliance_knowledge",
        sql="""
            SELECT
                id::text AS id,
                name,
                name_local,
                region_scope,
                issuing_body,
                technical_standards,
                regulation_basis,
                scope_description,
                requirements,
                testing_bodies,
                assessment_procedure,
                remarks
            FROM compliance_knowledge
            WHERE status = 'active'
            ORDER BY updated_at DESC
        """,
        fields=[
            "name",
            "name_local",
            "region_scope",
            "issuing_body",
            "technical_standards",
            "regulation_basis",
            "scope_description",
            "requirements",
            "testing_bodies",
            "assessment_procedure",
            "remarks",
        ],
    ),
    TableTranslationConfig(
        entity_type="official_sources",
        sql="""
            SELECT
                id::text AS id,
                name,
                source_type,
                entry_type_scope,
                last_error,
                parser_config
            FROM official_sources
            WHERE enabled = TRUE
            ORDER BY priority, updated_at DESC
        """,
        fields=["name", "source_type", "entry_type_scope", "last_error", "parser_config"],
    ),
    TableTranslationConfig(
        entity_type="source_records",
        sql="""
            SELECT
                id::text AS id,
                title,
                entry_type,
                discovery_method,
                source_status,
                source_payload
            FROM source_records
            ORDER BY updated_at DESC
        """,
        fields=["title", "entry_type", "discovery_method", "source_status", "source_payload"],
    ),
    TableTranslationConfig(
        entity_type="regulation_documents",
        sql="""
            SELECT
                id::text AS id,
                name,
                file_name,
                parse_error,
                progress_msg,
                spec_progress_msg
            FROM regulation_documents
            ORDER BY created_at DESC
        """,
        fields=["name", "file_name", "parse_error", "progress_msg", "spec_progress_msg"],
    ),
    TableTranslationConfig(
        entity_type="review_cases",
        sql="""
            SELECT
                id::text AS id,
                reasons,
                evidence_note,
                source_download_error
            FROM review_cases
            ORDER BY updated_at DESC
        """,
        fields=["reasons", "evidence_note", "source_download_error"],
    ),
    TableTranslationConfig(
        entity_type="country_source_coverage",
        sql="""
            SELECT
                country_code::text AS id,
                coverage_status,
                product_coverage_status,
                review_note,
                next_action
            FROM country_source_coverage
            ORDER BY updated_at DESC
        """,
        fields=["coverage_status", "product_coverage_status", "review_note", "next_action"],
    ),
    TableTranslationConfig(
        entity_type="regulation_spec_requirements",
        sql="""
            SELECT
                id::text AS id,
                regulation_name,
                module_en,
                title_en,
                description_en,
                verification_method_en,
                notes_en,
                regulation_clause,
                source_pages
            FROM regulation_spec_requirements
            ORDER BY updated_at DESC
        """,
        fields=[
            "regulation_name",
            "module_en",
            "title_en",
            "description_en",
            "verification_method_en",
            "notes_en",
            "regulation_clause",
            "source_pages",
        ],
    ),
]

DOCUMENT_TABLES: list[TableTranslationConfig] = [
    TableTranslationConfig(
        entity_type="regulation_document_sections",
        sql="""
            SELECT
                id::text AS id,
                title,
                section_path,
                section_ref,
                content
            FROM regulation_document_sections
            ORDER BY document_id, page_from, section_index
        """,
        fields=["title", "section_path", "section_ref", "content"],
    ),
]

CHUNK_TABLES: list[TableTranslationConfig] = [
    TableTranslationConfig(
        entity_type="regulation_document_chunks",
        sql="""
            SELECT
                id::text AS id,
                section_path,
                clause_ref,
                content
            FROM regulation_document_chunks
            ORDER BY document_id, chunk_index
        """,
        fields=["section_path", "clause_ref", "content"],
    ),
]


def _table_exists(table_name: str) -> bool:
    with get_cursor() as cur:
        cur.execute("SELECT to_regclass(%s) AS name", (f"public.{table_name}",))
        return bool(cur.fetchone()["name"])


def _select_rows(config: TableTranslationConfig, row_limit: int | None) -> list[dict[str, Any]]:
    table_name = config.entity_type
    if not _table_exists(table_name):
        logger.info("跳过不存在的表: %s", table_name)
        return []
    sql = config.sql
    params: tuple[Any, ...] = ()
    if row_limit:
        sql = f"SELECT * FROM ({config.sql}) t LIMIT %s"
        params = (row_limit,)
    with get_cursor() as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def collect_translation_jobs(
    profile: str,
    row_limit: int | None,
    entity_type: str | None = None,
) -> list[TranslationJob]:
    configs = list(METADATA_TABLES)
    if profile in {"documents", "all"}:
        configs.extend(DOCUMENT_TABLES)
    if profile == "all":
        configs.extend(CHUNK_TABLES)
    if entity_type:
        configs = [config for config in configs if config.entity_type == entity_type]
        if not configs:
            raise ValueError(f"不支持的 entity_type 或当前 profile 不包含该实体: {entity_type}")

    jobs: list[TranslationJob] = []
    for config in configs:
        rows = _select_rows(config, row_limit)
        table_jobs = build_translation_jobs(config.entity_type, rows, config.fields)
        logger.info(
            "翻译候选: %-32s rows=%d fields=%d jobs=%d",
            config.entity_type,
            len(rows),
            len(config.fields),
            len(table_jobs),
        )
        jobs.extend(table_jobs)
    return jobs


def iter_batches(jobs: list[TranslationJob], max_items: int, max_chars: int):
    batch: list[TranslationJob] = []
    char_count = 0
    for job in jobs:
        text_len = len(job.source_text)
        if batch and (len(batch) >= max_items or char_count + text_len > max_chars):
            yield batch
            batch = []
            char_count = 0
        batch.append(job)
        char_count += text_len
    if batch:
        yield batch


def translate_batch(batch: list[TranslationJob]) -> tuple[dict[str, str], str, str]:
    payload = {f"t{index}": job.source_text for index, job in enumerate(batch)}
    router = get_channel_router()
    response = router.chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "你是网络安全合规、法律法规和产品认证领域的专业翻译。"
                    "把输入翻译成简体中文。保留法规编号、条款号、日期、机构名、产品代号、标准号和常用英文缩写；"
                    "不要新增事实，不要解释，不要省略。只返回 JSON 对象，key 必须与输入一致，value 为中文翻译。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ],
        temperature=0.1,
        max_tokens=4096,
        enable_web_search=False,
        timeout=180,
    )
    return parse_translation_json(response.content), response.provider_name, response.model


def run(args: argparse.Namespace) -> int:
    jobs = collect_translation_jobs(args.profile, args.row_limit, args.entity_type)
    if args.limit:
        jobs = jobs[: args.limit]
    logger.info("总翻译字段候选: %d", len(jobs))
    if not jobs:
        return 0

    if args.dry_run:
        for job in jobs[:20]:
            logger.info(
                "DRY-RUN %s/%s/%s: %s",
                job.entity_type,
                job.entity_id,
                job.field_name,
                job.source_text[:120],
            )
        return 0

    upserted = upsert_translation_jobs(jobs, target_language=args.target_language)
    completed_by_hash = list_completed_translations_by_hash(
        [job.source_text_hash for job in jobs],
        target_language=args.target_language,
    )
    reused = store_reused_translations(
        jobs,
        completed_by_hash,
        target_language=args.target_language,
    )
    remaining = [job for job in jobs if job.source_text_hash not in completed_by_hash]

    jobs_by_hash: dict[str, list[TranslationJob]] = defaultdict(list)
    unique_remaining: list[TranslationJob] = []
    seen_hashes: set[str] = set()
    for job in remaining:
        jobs_by_hash[job.source_text_hash].append(job)
        if job.source_text_hash not in seen_hashes:
            unique_remaining.append(job)
            seen_hashes.add(job.source_text_hash)

    completed = 0
    failed = 0
    for batch in iter_batches(unique_remaining, args.batch_size, args.batch_chars):
        try:
            translations, provider_name, model = translate_batch(batch)
        except Exception as exc:
            logger.exception("翻译批次失败: %s", exc)
            for job in batch:
                for original_job in jobs_by_hash[job.source_text_hash]:
                    store_failed_translation(
                        original_job,
                        str(exc),
                        target_language=args.target_language,
                    )
                    failed += 1
            continue

        for index, job in enumerate(batch):
            translated_text = translations.get(f"t{index}")
            if not translated_text:
                error = "模型响应缺少对应翻译 key"
                for original_job in jobs_by_hash[job.source_text_hash]:
                    store_failed_translation(
                        original_job,
                        error,
                        target_language=args.target_language,
                    )
                    failed += 1
                continue
            for original_job in jobs_by_hash[job.source_text_hash]:
                store_completed_translation(
                    original_job,
                    translated_text,
                    target_language=args.target_language,
                    provider_name=provider_name,
                    model=model,
                )
                completed += 1
        logger.info(
            "翻译批次完成: unique=%d completed_fields=%d failed_fields=%d",
            len(batch),
            completed,
            failed,
        )

    logger.info(
        "翻译任务完成: queued=%d reused=%d newly_completed=%d failed=%d",
        upserted,
        reused,
        completed,
        failed,
    )
    return 0 if failed == 0 else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="将知识库外语字段翻译为中文并保留原文")
    parser.add_argument(
        "--profile",
        choices=["metadata", "documents", "all"],
        default="metadata",
        help="metadata=业务元数据；documents=加条款结构；all=再加RAG切片全文",
    )
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少个字段候选，0 表示不限")
    parser.add_argument("--row-limit", type=int, default=0, help="每张表最多读取多少行，0 表示不限")
    parser.add_argument("--batch-size", type=int, default=18)
    parser.add_argument("--batch-chars", type=int, default=6000)
    parser.add_argument("--target-language", default="zh-CN")
    parser.add_argument("--entity-type", help="只翻译指定实体表，例如 official_sources")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.limit = args.limit or None
    args.row_limit = args.row_limit or None
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
