"""
database/connection.py
数据库连接池管理 - 基于 psycopg2 连接池，线程安全
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import Generator, Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

from config.settings import get_settings

logger = logging.getLogger(__name__)

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """获取连接池单例（线程安全懒加载）"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _create_pool()
    return _pool


def _create_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """创建连接池，含重试逻辑"""
    settings = get_settings()
    db = settings.db

    max_retries = 5
    retry_delay = 3

    for attempt in range(1, max_retries + 1):
        try:
            pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=db.pool_min,
                maxconn=db.pool_max,
                dsn=db.dsn,
                connect_timeout=10,
                options="-c timezone=UTC",
            )
            logger.info(
                "✅ 数据库连接池创建成功 [%s:%s/%s, pool=%d~%d]",
                db.host, db.port, db.name, db.pool_min, db.pool_max,
            )
            return pool
        except psycopg2.OperationalError as e:
            if attempt == max_retries:
                logger.critical("❌ 数据库连接失败（已重试%d次）: %s", max_retries, e)
                raise
            logger.warning(
                "数据库连接失败（第%d/%d次），%ds后重试: %s",
                attempt, max_retries, retry_delay, e,
            )
            time.sleep(retry_delay)


@contextlib.contextmanager
def get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    从连接池获取连接的上下文管理器。
    自动处理事务提交/回滚和连接归还。

    用法:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = False
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextlib.contextmanager
def get_cursor(
    cursor_factory=psycopg2.extras.RealDictCursor,
) -> Generator[psycopg2.extensions.cursor, None, None]:
    """
    便捷上下文管理器，直接获取 cursor（返回字典行）。

    用法:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM countries")
            rows = cur.fetchall()
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=cursor_factory) as cur:
            yield cur


def close_pool() -> None:
    """关闭连接池（程序退出时调用）"""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("数据库连接池已关闭")


def health_check() -> dict:
    """数据库健康检查，返回状态信息"""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT version(), NOW() AT TIME ZONE 'UTC' AS server_time")
            row = cur.fetchone()
        return {
            "status": "healthy",
            "server_time": str(row["server_time"]),
            "version": row["version"][:50],
        }
    except Exception as e:
        logger.error("数据库健康检查失败: %s", e)
        return {"status": "unhealthy", "error": str(e)}
