#!/usr/bin/env python3
"""
scripts/init_db.py
数据库初始化脚本：创建数据库、用户、执行迁移和种子数据

用法:
    # 方式1：使用超级用户初始化（推荐首次）
    python scripts/init_db.py --superuser postgres --superpass yourpass

    # 方式2：数据库已存在，只执行迁移
    python scripts/init_db.py --migrate-only

    # 方式3：完整初始化 + 种子数据
    python scripts/init_db.py --superuser postgres --superpass yourpass --seed
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
import psycopg2.extensions

from config.settings import get_settings
from utils.logger import setup_logging

setup_logging(level="INFO")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
MIGRATIONS_DIR = BASE_DIR / "database" / "migrations"
SEEDS_DIR = BASE_DIR / "database" / "seeds"


def migration_version(sql_file: Path) -> int:
    """Return numeric migration version from names like V12__name.sql."""
    match = re.match(r"V(\d+)__", sql_file.name)
    if not match:
        raise ValueError(f"迁移文件命名不合法: {sql_file.name}")
    return int(match.group(1))


def ensure_migration_table(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    INTEGER PRIMARY KEY,
                filename   TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def has_existing_schema(conn: psycopg2.extensions.connection) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.compliance_knowledge') IS NOT NULL")
        return bool(cur.fetchone()[0])


def baseline_existing_migrations(
    conn: psycopg2.extensions.connection,
    sql_files: list[Path],
) -> None:
    """Mark current migrations as applied for legacy databases without tracking."""
    with conn.cursor() as cur:
        for sql_file in sql_files:
            cur.execute(
                """
                INSERT INTO schema_migrations (version, filename)
                VALUES (%s, %s)
                ON CONFLICT (version) DO NOTHING
                """,
                (migration_version(sql_file), sql_file.name),
            )
    conn.commit()
    logger.info("ℹ️  已为现有数据库建立迁移基线，共 %s 个版本", len(sql_files))


def create_database_and_user(
    superuser: str,
    superpass: str,
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str,
) -> None:
    """使用超级用户创建数据库和应用用户"""
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=superuser,
        password=superpass,
        dbname="postgres",
    )
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

    with conn.cursor() as cur:
        # 创建用户（如不存在）
        cur.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s",
            (db_user,),
        )
        if not cur.fetchone():
            cur.execute(
                f"CREATE USER {db_user} WITH PASSWORD %s",
                (db_password,),
            )
            logger.info("✅ 创建数据库用户: %s", db_user)
        else:
            logger.info("ℹ️  用户已存在: %s", db_user)

        # 创建数据库（如不存在）
        cur.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,),
        )
        if not cur.fetchone():
            cur.execute(
                f'CREATE DATABASE {db_name} OWNER {db_user} '
                f"ENCODING 'UTF8' LC_COLLATE 'en_US.UTF-8' LC_CTYPE 'en_US.UTF-8' TEMPLATE template0"
            )
            logger.info("✅ 创建数据库: %s", db_name)
        else:
            logger.info("ℹ️  数据库已存在: %s", db_name)

        # 授权
        cur.execute(f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user}")
        logger.info("✅ 权限授予完成")

    conn.close()


def install_database_extensions(
    superuser: str,
    superpass: str,
    db_host: str,
    db_port: int,
    db_name: str,
) -> None:
    """Install extensions that require elevated privileges before app migrations."""
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=superuser,
        password=superpass,
        dbname=db_name,
    )
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

    with conn.cursor() as cur:
        for extension in ("uuid-ossp", "pgcrypto", "pg_trgm", "vector"):
            cur.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}"')
            logger.info("✅ 数据库扩展已就绪: %s", extension)

    conn.close()


def execute_sql_file(
    conn: psycopg2.extensions.connection,
    sql_file: Path,
) -> None:
    """执行 SQL 文件"""
    logger.info("⚙️  执行: %s", sql_file.name)
    sql_content = sql_file.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql_content)
    conn.commit()
    logger.info("✅ 完成: %s", sql_file.name)


def run_migrations(db_dsn: str) -> None:
    """按版本顺序执行迁移文件"""
    sql_files = sorted(MIGRATIONS_DIR.glob("V*.sql"), key=migration_version)
    if not sql_files:
        logger.warning("未找到迁移文件: %s", MIGRATIONS_DIR)
        return

    conn = psycopg2.connect(dsn=db_dsn, options="-c timezone=UTC")
    try:
        ensure_migration_table(conn)

        with conn.cursor() as cur:
            cur.execute("SELECT version FROM schema_migrations")
            applied = {row[0] for row in cur.fetchall()}

        if not applied and has_existing_schema(conn):
            baseline_existing_migrations(conn, sql_files)
            applied = {migration_version(sql_file) for sql_file in sql_files}

        for sql_file in sql_files:
            version = migration_version(sql_file)
            if version in applied:
                logger.info("⏭️  跳过已应用迁移: %s", sql_file.name)
                continue
            execute_sql_file(conn, sql_file)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO schema_migrations (version, filename)
                    VALUES (%s, %s)
                    ON CONFLICT (version) DO UPDATE SET
                        filename = EXCLUDED.filename,
                        applied_at = NOW()
                    """,
                    (version, sql_file.name),
                )
            conn.commit()
    finally:
        conn.close()


def run_seeds(db_dsn: str) -> None:
    """执行种子数据文件"""
    sql_files = sorted(SEEDS_DIR.glob("V*.sql"))
    if not sql_files:
        logger.warning("未找到种子数据文件: %s", SEEDS_DIR)
        return

    conn = psycopg2.connect(dsn=db_dsn, options="-c timezone=UTC")
    try:
        for sql_file in sql_files:
            execute_sql_file(conn, sql_file)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="数据库初始化脚本")
    parser.add_argument("--superuser", help="PostgreSQL 超级用户名（如 postgres）")
    parser.add_argument("--superpass", help="超级用户密码")
    parser.add_argument("--migrate-only", action="store_true", help="只执行迁移，跳过建库")
    parser.add_argument("--seed", action="store_true", help="导入种子数据")
    parser.add_argument("--seed-only", action="store_true", help="只导入种子数据")
    args = parser.parse_args()

    settings = get_settings()
    db = settings.db

    logger.info("=" * 60)
    logger.info("  网安合规助手 - 数据库初始化")
    logger.info("  目标: %s:%s/%s", db.host, db.port, db.name)
    logger.info("=" * 60)

    # Step 1: 创建数据库和用户
    if not args.migrate_only and not args.seed_only:
        if not args.superuser:
            logger.error("❌ 首次初始化需要提供 --superuser 参数")
            sys.exit(1)
        superpass = args.superpass or os.environ.get("PGPASSWORD", "")
        create_database_and_user(
            superuser=args.superuser,
            superpass=superpass,
            db_host=db.host,
            db_port=db.port,
            db_name=db.name,
            db_user=db.user,
            db_password=db.password,
        )
        install_database_extensions(
            superuser=args.superuser,
            superpass=superpass,
            db_host=db.host,
            db_port=db.port,
            db_name=db.name,
        )

    # Step 2: 执行迁移
    if not args.seed_only:
        run_migrations(db.dsn)

    # Step 3: 种子数据
    if args.seed or args.seed_only:
        run_seeds(db.dsn)

    logger.info("")
    logger.info("🎉 数据库初始化完成！")
    logger.info("   下一步: cp config/.env.example config/.env")
    logger.info("   然后编辑 config/.env 填入 API Key 等配置")


if __name__ == "__main__":
    main()
