"""Bilingual translation service primitives.

The project stores official evidence in its original language. Translation is
an additive layer: never mutate source fields, only attach Chinese renderings.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


URL_RE = re.compile(r"^https?://", re.I)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T\s].*)?$")
CODE_RE = re.compile(r"^[A-Z]{1,4}\d?$")
SNAKE_CODE_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")
NON_TRANSLATABLE_WORDS = {
    "active",
    "deprecated",
    "draft",
    "superseded",
    "candidate",
    "verified",
    "suspicious",
    "quarantined",
    "mandatory",
    "voluntary",
    "recommended",
    "pending",
    "failed",
    "downloaded",
    "ready",
}


@dataclass(frozen=True)
class TranslationField:
    field_name: str
    source_text: str


@dataclass(frozen=True)
class TranslationJob:
    entity_type: str
    entity_id: str
    field_name: str
    source_text: str
    source_text_hash: str


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def stable_text_hash(value: str) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def is_translatable_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = normalize_text(value)
    if len(text) < 4:
        return False
    lowered = text.lower()
    if lowered in NON_TRANSLATABLE_WORDS:
        return False
    if CJK_RE.search(text) and not LATIN_RE.search(text):
        return False
    if URL_RE.match(text) or DATE_RE.match(text) or CODE_RE.match(text) or SNAKE_CODE_RE.match(text):
        return False
    if re.fullmatch(r"[\d\s.,:/_\-+()]+", text):
        return False
    return True


def extract_text_values(field_name: str, value: Any) -> list[TranslationField]:
    """Extract translatable strings from scalar/list/dict fields.

    Nested fields use a stable dotted path so translated JSON leaves can be
    attached without replacing the original JSON payload.
    """
    results: list[TranslationField] = []

    def walk(path: str, current: Any) -> None:
        if isinstance(current, str):
            text = normalize_text(current)
            if is_translatable_value(text):
                results.append(TranslationField(path, text))
            return
        if isinstance(current, list):
            for index, item in enumerate(current):
                walk(f"{path}[{index}]", item)
            return
        if isinstance(current, dict):
            for key in current:
                walk(f"{path}.{key}", current[key])

    walk(field_name, value)
    return results


def attach_translation_fields(
    row: Mapping[str, Any],
    translations: Mapping[tuple[str, str], str],
    entity_id_field: str = "id",
) -> dict[str, Any]:
    enriched = dict(row)
    entity_id = str(row.get(entity_id_field) or "")
    row_translations: dict[str, str] = {}
    for (translated_entity_id, field_name), translated_text in translations.items():
        if str(translated_entity_id) != entity_id or not translated_text:
            continue
        row_translations[field_name] = translated_text
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field_name):
            enriched[f"{field_name}_zh"] = translated_text
    if row_translations:
        enriched["translations"] = row_translations
    return enriched


def build_translation_jobs(
    entity_type: str,
    rows: list[Mapping[str, Any]],
    translatable_fields: list[str],
    entity_id_field: str = "id",
) -> list[TranslationJob]:
    jobs: list[TranslationJob] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        entity_id = str(row.get(entity_id_field) or "")
        if not entity_id:
            continue
        for field_name in translatable_fields:
            for extracted in extract_text_values(field_name, row.get(field_name)):
                text_hash = stable_text_hash(extracted.source_text)
                key = (entity_id, extracted.field_name, text_hash)
                if key in seen:
                    continue
                seen.add(key)
                jobs.append(
                    TranslationJob(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        field_name=extracted.field_name,
                        source_text=extracted.source_text,
                        source_text_hash=text_hash,
                    )
                )
    return jobs


def merge_hash_reuse(
    pending: list[TranslationJob],
    existing_by_hash: Mapping[str, str],
) -> tuple[dict[tuple[str, str, str, str], str], list[TranslationJob]]:
    reused: dict[tuple[str, str, str, str], str] = {}
    remaining: list[TranslationJob] = []
    for job in pending:
        translated = existing_by_hash.get(job.source_text_hash)
        if translated:
            reused[
                (job.entity_type, job.entity_id, job.field_name, job.source_text_hash)
            ] = translated
        else:
            remaining.append(job)
    return reused, remaining


def parse_translation_json(content: str) -> dict[str, str]:
    """Parse model output for translation batches.

    The prompt asks for a JSON object. This helper tolerates fenced JSON and
    rejects non-string values instead of storing unsafe structures.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("translation response must be a JSON object")
    return {str(key): normalize_text(value) for key, value in parsed.items() if isinstance(value, str)}
