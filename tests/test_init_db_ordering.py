from pathlib import Path

from scripts import init_db


def test_migration_files_sort_by_numeric_version():
    files = [
        Path("database/migrations/V10__expanded_official_sources.sql"),
        Path("database/migrations/V1__init_schema.sql"),
        Path("database/migrations/V3__rag_documents.sql"),
    ]

    ordered = init_db.sort_versioned_sql_files(files)

    assert [path.name for path in ordered] == [
        "V1__init_schema.sql",
        "V3__rag_documents.sql",
        "V10__expanded_official_sources.sql",
    ]
