#!/usr/bin/env python3
"""Record country-level research outcomes for product cybersecurity regimes.

This script is intentionally separate from compliance record creation. It is used when
official source review finds no standalone product-level cybersecurity certification,
label, market-access, or technical-security regime for a country.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.connection import get_connection


DEFAULT_OUTCOME_STATUS = "no_product_regime_found_verified"


def _split_urls(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).replace("\n", ",").split(",") if part.strip()]


def load_outcomes(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        outcomes: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                outcomes.append(json.loads(line))
        return outcomes

    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize(outcomes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in outcomes:
        country_code = str(row.get("country_code") or "").strip().upper()
        review_note = str(row.get("review_note") or "").strip()
        if not country_code or not review_note:
            raise ValueError("Each outcome requires country_code and review_note")
        normalized.append(
            {
                "country_code": country_code,
                "outcome_status": str(row.get("outcome_status") or DEFAULT_OUTCOME_STATUS).strip(),
                "review_note": review_note,
                "evidence_urls": _split_urls(row.get("evidence_urls")),
                "checked_by": str(row.get("checked_by") or "official-source-research").strip(),
            }
        )
    return normalized


def seed(outcomes: Iterable[dict[str, Any]]) -> int:
    rows = normalize(outcomes)
    updated = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute("SELECT 1 FROM countries WHERE code=%s AND enabled=TRUE", (row["country_code"],))
                if cur.fetchone() is None:
                    continue
                cur.execute(
                    """
                    INSERT INTO country_product_research_outcomes (
                        country_code,
                        outcome_status,
                        review_note,
                        evidence_urls,
                        checked_by,
                        checked_at
                    )
                    VALUES (
                        %(country_code)s,
                        %(outcome_status)s,
                        %(review_note)s,
                        %(evidence_urls)s,
                        %(checked_by)s,
                        NOW()
                    )
                    ON CONFLICT (country_code) DO UPDATE SET
                        outcome_status=EXCLUDED.outcome_status,
                        review_note=EXCLUDED.review_note,
                        evidence_urls=EXCLUDED.evidence_urls,
                        checked_by=EXCLUDED.checked_by,
                        checked_at=NOW(),
                        updated_at=NOW()
                    RETURNING 1
                    """,
                    row,
                )
                if cur.fetchone():
                    updated += 1
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True, help="CSV or JSONL file with product research outcomes")
    args = parser.parse_args()

    updated = seed(load_outcomes(args.file))
    print(f"product research outcomes seeded: updated={updated}")


if __name__ == "__main__":
    main()
