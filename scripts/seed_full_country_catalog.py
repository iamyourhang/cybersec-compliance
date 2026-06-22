#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.connection import get_connection
from scripts.country_catalog import FULL_COUNTRY_CATALOG


def seed(dry_run: bool = False) -> dict[str, Any]:
    inserted = 0
    updated = 0
    existing_count = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM countries")
            existing_count = int(cur.fetchone()[0])
            if dry_run:
                cur.execute("SELECT code FROM countries")
                existing_codes = {row[0] for row in cur.fetchall()}
                missing = [item["code"] for item in FULL_COUNTRY_CATALOG if item["code"] not in existing_codes]
                return {
                    "dry_run": True,
                    "existing": existing_count,
                    "catalog": len(FULL_COUNTRY_CATALOG),
                    "missing": len(missing),
                    "missing_codes": missing,
                }

            for item in FULL_COUNTRY_CATALOG:
                cur.execute(
                    """
                    INSERT INTO countries (code, name_zh, name_en, region, priority, jurisdiction_type, enabled)
                    VALUES (
                        %(code)s,
                        %(name_zh)s,
                        %(name_en)s,
                        %(region)s,
                        %(priority)s,
                        %(jurisdiction_type)s,
                        TRUE
                    )
                    ON CONFLICT (code) DO UPDATE SET
                        name_zh=EXCLUDED.name_zh,
                        name_en=EXCLUDED.name_en,
                        region=EXCLUDED.region,
                        jurisdiction_type=EXCLUDED.jurisdiction_type,
                        enabled=TRUE,
                        updated_at=NOW()
                    RETURNING (xmax = 0) AS inserted
                    """,
                    item,
                )
                if cur.fetchone()[0]:
                    inserted += 1
                else:
                    updated += 1

    return {
        "dry_run": False,
        "existing_before": existing_count,
        "catalog": len(FULL_COUNTRY_CATALOG),
        "inserted": inserted,
        "updated": updated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the complete country/jurisdiction target catalog for global cybersecurity compliance tracking."
    )
    parser.add_argument("--dry-run", action="store_true", help="Only report missing country codes without writing.")
    args = parser.parse_args()

    result = seed(dry_run=args.dry_run)
    if result["dry_run"]:
        print(
            "full country catalog dry-run: "
            f"existing={result['existing']}, catalog={result['catalog']}, missing={result['missing']}"
        )
        if result["missing_codes"]:
            print("missing_codes=" + ",".join(result["missing_codes"]))
    else:
        print(
            "full country catalog seeded: "
            f"existing_before={result['existing_before']}, catalog={result['catalog']}, "
            f"inserted={result['inserted']}, updated={result['updated']}"
        )


if __name__ == "__main__":
    main()
