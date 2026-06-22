"""
collector/document/doc_repository.py
regulation_documents 表的数据访问层
只负责数据库读写，不含业务逻辑
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional
from database.connection import get_connection, get_cursor

logger = logging.getLogger(__name__)


class DocRepository:

    @staticmethod
    def create(data: Dict[str, Any]) -> str:
        """创建文档记录，返回 UUID"""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO regulation_documents
                        (compliance_id, name, country_code, file_name, cos_key, cos_url,
                         file_size, file_type, parse_status, index_status, uploaded_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pending','pending',%s)
                    RETURNING id
                """, (
                    data.get("compliance_id"), data["name"], data["country_code"], data["file_name"],
                    data["cos_key"], data.get("cos_url"), data.get("file_size"),
                    data.get("file_type", "pdf"), data.get("uploaded_by"),
                ))
                doc_id = str(cur.fetchone()[0])
        logger.info("📄 文档记录创建: %s [%s]", data["name"][:60], doc_id)
        return doc_id

    @staticmethod
    def get(doc_id: str) -> Optional[Dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM regulation_documents WHERE id=%s", (doc_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def list(
        country_code: Optional[str] = None,
        parse_status: Optional[str] = None,
        index_status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        sql = "SELECT * FROM regulation_documents WHERE 1=1"
        params = []
        if country_code:
            sql += " AND country_code=%s"; params.append(country_code)
        if parse_status:
            sql += " AND parse_status=%s"; params.append(parse_status)
        if index_status:
            sql += " AND index_status=%s"; params.append(index_status)
        sql += " ORDER BY created_at DESC LIMIT %s"; params.append(limit)
        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def list_pending_source_documents(limit: int = 20) -> List[Dict]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM regulation_documents
                WHERE parse_status='pending'
                  AND uploaded_by='system:official_source'
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def set_parsing(doc_id: str) -> None:
        """标记为解析中"""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE regulation_documents SET parse_status='parsing' WHERE id=%s",
                    (doc_id,)
                )

    @staticmethod
    def set_parsed(doc_id: str, result: Dict, compliance_id: Optional[str] = None) -> None:
        """标记解析成功，存储结果"""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE regulation_documents
                    SET parse_status='done', parse_result=%s,
                        parsed_at=NOW(), compliance_id=COALESCE(%s, compliance_id),
                        progress=100, progress_msg='结构化解析完成'
                    WHERE id=%s
                """, (json.dumps(result, ensure_ascii=False, default=str), compliance_id, doc_id))
        logger.info("✅ 文档解析完成: %s", doc_id)

    @staticmethod
    def set_failed(doc_id: str, error: str) -> None:
        """标记解析失败"""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE regulation_documents
                    SET parse_status='failed', parse_error=%s, progress=100, progress_msg='结构化解析失败'
                    WHERE id=%s
                    """,
                    (error[:1000], doc_id)
                )
        logger.warning("❌ 文档解析失败: %s - %s", doc_id, error[:100])

    @staticmethod
    def set_indexing(doc_id: str, progress: int, msg: str) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE regulation_documents
                    SET index_status='indexing', index_error=NULL,
                        progress=%s, progress_msg=%s
                    WHERE id=%s
                    """,
                    (max(0, min(100, progress)), msg[:200], doc_id),
                )

    @staticmethod
    def set_indexed(doc_id: str, page_count: int, chunk_count: int, content_hash: str) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE regulation_documents
                    SET index_status='ready', indexed_at=NOW(),
                        page_count=%s, chunk_count=%s, content_hash=%s,
                        progress=100, progress_msg='结构化解析与索引完成'
                    WHERE id=%s
                    """,
                    (page_count, chunk_count, content_hash, doc_id),
                )

    @staticmethod
    def set_index_diagnostics(doc_id: str, diagnostics: Dict[str, Any]) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE regulation_documents
                    SET parse_result = COALESCE(parse_result, '{}'::jsonb) || %s::jsonb
                    WHERE id=%s
                    """,
                    (json.dumps({"index_diagnostics": diagnostics}, ensure_ascii=False), doc_id),
                )

    @staticmethod
    def set_index_failed(doc_id: str, error: str) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE regulation_documents
                    SET index_status='failed', index_error=%s,
                        progress=100, progress_msg='索引失败'
                    WHERE id=%s
                    """,
                    (error[:1000], doc_id),
                )

    @staticmethod
    def link_compliance(doc_id: str, compliance_id: str) -> None:
        """关联到知识库条目"""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE regulation_documents SET compliance_id=%s WHERE id=%s",
                    (compliance_id, doc_id)
                )

    @staticmethod
    def delete(doc_id: str) -> Optional[str]:
        """删除记录，返回 cos_key 供调用方清理 COS"""
        with get_cursor() as cur:
            cur.execute("SELECT cos_key FROM regulation_documents WHERE id=%s", (doc_id,))
            row = cur.fetchone()
        if not row:
            return None
        cos_key = row["cos_key"]
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM regulation_documents WHERE id=%s", (doc_id,))
        return cos_key

    @staticmethod
    def set_progress(doc_id: str, progress: int, msg: str) -> None:
        """更新任务进度 0-100"""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE regulation_documents SET progress=%s, progress_msg=%s WHERE id=%s",
                        (max(0, min(100, progress)), msg[:200], doc_id)
                    )
        except Exception as e:
            logger.warning("进度更新失败: %s", e)

    @staticmethod
    def set_spec_progress(doc_id: str, progress: int, msg: str) -> None:
        """更新规格生成进度 0-100"""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE regulation_documents SET spec_progress=%s, spec_progress_msg=%s WHERE id=%s",
                        (max(0, min(100, progress)), msg[:200], doc_id)
                    )
        except Exception as e:
            logger.warning("规格进度更新失败: %s", e)

    @staticmethod
    def reset_spec_progress(doc_id: str, msg: str = "等待生成规格") -> None:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE regulation_documents
                        SET spec_progress=0,
                            spec_progress_msg=%s
                        WHERE id=%s
                        """,
                        (msg[:200], doc_id),
                    )
        except Exception as e:
            logger.warning("规格进度重置失败: %s", e)

    @staticmethod
    def set_spec_generated(doc_id: str, cos_url: str, cos_key: str, stored_count: int) -> None:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE regulation_documents
                        SET spec_cos_url=%s,
                            spec_cos_key=%s,
                            spec_generated_at=NOW(),
                            spec_requirement_count=%s,
                            spec_progress=100,
                            spec_progress_msg='规格生成完成'
                        WHERE id=%s
                        """,
                        (cos_url, cos_key, max(0, int(stored_count or 0)), doc_id),
                    )
        except Exception as e:
            logger.warning("规格生成结果写入失败: %s", e)
