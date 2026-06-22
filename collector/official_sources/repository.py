from __future__ import annotations

import json
from typing import Any, Optional

from database.connection import get_connection, get_cursor


class OfficialSourceRepository:
    def list_all(
        self,
        country_priorities: Optional[list[str]] = None,
        enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT os.*, c.priority AS country_priority, c.name_zh AS country_name
            FROM official_sources os
            JOIN countries c ON os.country_code = c.code
            WHERE 1=1
        """
        params: list[Any] = []
        if enabled_only:
            sql += " AND os.enabled = TRUE"
        if country_priorities:
            sql += " AND c.priority::text = ANY(%s)"
            params.append(country_priorities)
        sql += " ORDER BY os.priority, os.created_at"
        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def get_by_id(self, source_id: str) -> Optional[dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT os.*, c.priority AS country_priority, c.name_zh AS country_name
                FROM official_sources os
                JOIN countries c ON os.country_code = c.code
                WHERE os.id = %s
                """,
                (source_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO official_sources
                        (country_code, name, base_url, list_url, source_type, allowed_domains,
                         entry_type_scope, poll_interval_hours, priority, enabled, parser_config)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        payload["country_code"],
                        payload["name"],
                        payload["base_url"],
                        payload["list_url"],
                        payload["source_type"],
                        payload.get("allowed_domains", []),
                        payload.get("entry_type_scope", []),
                        payload.get("poll_interval_hours", 24),
                        payload.get("priority", 100),
                        payload.get("enabled", True),
                        json.dumps(payload.get("parser_config") or {}, ensure_ascii=False),
                    ),
                )
                source_id = cur.fetchone()[0]
        return self.get_by_id(str(source_id))

    def update(self, source_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        fields = {
            "country_code": payload["country_code"],
            "name": payload["name"],
            "base_url": payload["base_url"],
            "list_url": payload["list_url"],
            "source_type": payload["source_type"],
            "allowed_domains": payload.get("allowed_domains", []),
            "entry_type_scope": payload.get("entry_type_scope", []),
            "poll_interval_hours": payload.get("poll_interval_hours", 24),
            "priority": payload.get("priority", 100),
            "enabled": payload.get("enabled", True),
            "parser_config": json.dumps(payload.get("parser_config") or {}, ensure_ascii=False),
        }
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE official_sources
                    SET country_code=%(country_code)s,
                        name=%(name)s,
                        base_url=%(base_url)s,
                        list_url=%(list_url)s,
                        source_type=%(source_type)s,
                        allowed_domains=%(allowed_domains)s,
                        entry_type_scope=%(entry_type_scope)s,
                        poll_interval_hours=%(poll_interval_hours)s,
                        priority=%(priority)s,
                        enabled=%(enabled)s,
                        parser_config=%(parser_config)s::jsonb,
                        updated_at=NOW()
                    WHERE id=%(source_id)s
                    """,
                    {**fields, "source_id": source_id},
                )
                if cur.rowcount == 0:
                    return None
        return self.get_by_id(source_id)

    def record_history(
        self,
        source_id: str,
        status: str,
        discovered_count: int = 0,
        candidate_count: int = 0,
        artifact_count: int = 0,
        error: Optional[str] = None,
    ) -> None:
        success_like = status.startswith("success")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO official_source_history
                        (source_id, status, discovered_count, candidate_count, artifact_count, error)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (source_id, status, discovered_count, candidate_count, artifact_count, error),
                )
                cur.execute(
                    """
                    UPDATE official_sources
                    SET last_checked_at=NOW(),
                        last_success_at=CASE WHEN %s THEN NOW() ELSE last_success_at END,
                        last_error=CASE WHEN %s THEN NULL ELSE %s END,
                        updated_at=NOW()
                    WHERE id=%s
                    """,
                    (success_like, success_like, error[:1000] if error else None, source_id),
                )

    def list_history(self, source_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, source_id, status, discovered_count, candidate_count,
                       artifact_count, error, started_at
                FROM official_source_history
                WHERE source_id=%s
                ORDER BY started_at DESC LIMIT %s
                """,
                (source_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]


def get_official_source_repository() -> OfficialSourceRepository:
    return OfficialSourceRepository()
