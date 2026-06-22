"""
collector/providers/channel_repository.py
LLM 通道池与事件日志仓储。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import psycopg2.extras
from app.security.crypto import decrypt_secret
from app.security.crypto import encrypt_secret
from collector.providers.dashscope import _build_qwen_extra_body
from collector.providers.router_models import ChannelConfig
from config.settings import get_settings
from database.connection import get_connection, get_cursor

logger = logging.getLogger(__name__)


def _normalize_openai_base_url(base_url: str) -> str:
    parsed = urlparse((base_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return base_url
    path = (parsed.path or "").rstrip("/")
    if path:
        return base_url.rstrip("/")
    return f"{base_url.rstrip('/')}/v1"


def _model_supports_enable_search(model: str) -> bool:
    return bool(_build_qwen_extra_body(model, enable_web_search=True))


class ChannelRepository:
    def __init__(self):
        self._settings = get_settings()

    def list_routable_channels(self) -> List[ChannelConfig]:
        override = self._load_uniapi_override_channel()
        rows = self._list_enabled_db_channels()
        if rows:
            if override and all(channel.id != override.id for channel in rows):
                return [override] + rows
            return rows
        env_channels = self._load_env_fallback_channels()
        if override and all(channel.id != override.id for channel in env_channels):
            return [override] + env_channels
        return env_channels

    def list_all(self) -> List[Dict[str, Any]]:
        override = self._load_uniapi_override_channel()
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, name, provider_type, base_url, model, priority,
                       enabled, supports_web_search, quota_exhausted,
                       manual_pause, last_error, last_checked_at,
                       created_at, updated_at
                FROM llm_channels
                ORDER BY priority, created_at
                """
            )
            items = [dict(row) for row in cur.fetchall()]
        if items:
            for row in items:
                row["source"] = "database"
            if override:
                items = [self._channel_to_row(override, source="env_override", order=0)] + items
            return items
        rows = self._load_env_fallback_rows()
        if override and all(row["id"] != override.id for row in rows):
            rows = [self._channel_to_row(override, source="env_override", order=0)] + rows
        return rows

    def get_channel(self, channel_id: str) -> Optional[ChannelConfig]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, name, provider_type, base_url, api_key_encrypted, model, priority,
                       enabled, supports_web_search, quota_exhausted, manual_pause
                FROM llm_channels
                WHERE id::text = %s
                """,
                (channel_id,),
            )
            row = cur.fetchone()
        if row:
            row_dict = dict(row)
            api_key = (
                decrypt_secret(row_dict["api_key_encrypted"], self._settings.llm_router_secret)
                if self._settings.llm_router_secret and row_dict.get("api_key_encrypted")
                else ""
            )
            return ChannelConfig(
                id=str(row_dict["id"]),
                name=row_dict["name"],
                provider_type=row_dict["provider_type"],
                base_url=row_dict["base_url"],
                api_key=api_key,
                model=row_dict["model"],
                priority=row_dict["priority"],
                enabled=row_dict["enabled"],
                supports_web_search=row_dict["supports_web_search"],
                quota_exhausted=row_dict["quota_exhausted"],
                manual_pause=row_dict["manual_pause"],
            )
        for channel in self._load_env_fallback_channels():
            if channel.id == channel_id:
                return channel
        return None

    def create_channel(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        encrypted_key = self._encrypt_api_key(payload["api_key"])
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO llm_channels (
                        name, provider_type, base_url, api_key_encrypted, model,
                        priority, enabled, supports_web_search
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, name, provider_type, base_url, model, priority,
                              enabled, supports_web_search, quota_exhausted,
                              manual_pause, last_error, last_checked_at,
                              created_at, updated_at
                    """,
                    (
                        payload["name"],
                        payload["provider_type"],
                        payload["base_url"],
                        encrypted_key,
                        payload["model"],
                        payload.get("priority", 100),
                        payload.get("enabled", True),
                        payload.get("supports_web_search", False),
                    ),
                )
                row = dict(cur.fetchone())
                row["source"] = "database"
                return row

    def update_channel(self, channel_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        fields = [
            "name = %s",
            "provider_type = %s",
            "base_url = %s",
            "model = %s",
            "priority = %s",
            "enabled = %s",
            "supports_web_search = %s",
            "updated_at = NOW()",
        ]
        params: List[Any] = [
            payload["name"],
            payload["provider_type"],
            payload["base_url"],
            payload["model"],
            payload.get("priority", 100),
            payload.get("enabled", True),
            payload.get("supports_web_search", False),
        ]
        if payload.get("api_key"):
            fields.append("api_key_encrypted = %s")
            params.append(self._encrypt_api_key(payload["api_key"]))
        params.append(channel_id)

        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    UPDATE llm_channels
                    SET {", ".join(fields)}
                    WHERE id = %s
                    RETURNING id, name, provider_type, base_url, model, priority,
                              enabled, supports_web_search, quota_exhausted,
                              manual_pause, last_error, last_checked_at,
                              created_at, updated_at
                    """,
                    params,
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = dict(row)
                result["source"] = "database"
                return result

    def mark_quota_exhausted(self, channel_id: str, error: str) -> bool:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE llm_channels
                    SET quota_exhausted = TRUE,
                        last_error = %s,
                        last_checked_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (error[:1000], channel_id),
                )
                return cur.rowcount > 0

    def clear_quota_exhausted(self, channel_id: str) -> bool:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE llm_channels
                    SET quota_exhausted = FALSE,
                        last_checked_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (channel_id,),
                )
                return cur.rowcount > 0

    def set_manual_pause(self, channel_id: str, paused: bool) -> bool:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE llm_channels
                    SET manual_pause = %s,
                        last_checked_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (paused, channel_id),
                )
                return cur.rowcount > 0

    def add_event(
        self,
        channel_id: str,
        event_type: str,
        message: Optional[str],
        raw_error: Optional[str],
    ) -> None:
        if not self._is_database_channel_id(channel_id):
            return
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO llm_channel_events (channel_id, event_type, message, raw_error)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        channel_id,
                        event_type,
                        (message or "")[:1000] or None,
                        (raw_error or "")[:2000] or None,
                    ),
                )

    def list_events(self, channel_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not self._is_database_channel_id(channel_id):
            return []
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, channel_id, event_type, message, raw_error, created_at
                FROM llm_channel_events
                WHERE channel_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (channel_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def _list_enabled_db_channels(self) -> List[ChannelConfig]:
        try:
            with get_cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, provider_type, base_url, api_key_encrypted, model, priority,
                           enabled, supports_web_search, quota_exhausted, manual_pause
                    FROM llm_channels
                    WHERE enabled = TRUE
                    ORDER BY priority, created_at
                    """
                )
                rows = cur.fetchall()
        except Exception as exc:
            logger.warning("读取 llm_channels 失败，回退到 .env 通道: %s", exc)
            return []

        key = self._settings.llm_router_secret
        channels: List[ChannelConfig] = []
        for row in rows:
            row_dict = dict(row)
            api_key = (
                decrypt_secret(row_dict["api_key_encrypted"], key)
                if key and row_dict.get("api_key_encrypted")
                else ""
            )
            channels.append(
                ChannelConfig(
                    id=str(row_dict["id"]),
                    name=row_dict["name"],
                    provider_type=row_dict["provider_type"],
                    base_url=row_dict["base_url"],
                    api_key=api_key,
                    model=row_dict["model"],
                    priority=row_dict["priority"],
                    enabled=row_dict["enabled"],
                    supports_web_search=row_dict["supports_web_search"],
                    quota_exhausted=row_dict["quota_exhausted"],
                    manual_pause=row_dict["manual_pause"],
                )
            )
        return channels

    def _load_env_fallback_channels(self) -> List[ChannelConfig]:
        channels: List[ChannelConfig] = []
        configured_items = self._settings.llm_router_fallback or self._load_legacy_env_channels()
        for index, item in enumerate(configured_items, start=1):
            channels.append(
                ChannelConfig(
                    id=item.get("id", item.get("name", f"fallback-{index}")),
                    name=item["name"],
                    provider_type=item["provider_type"],
                    base_url=item["base_url"],
                    api_key=item["api_key"],
                    model=item["model"],
                    priority=item.get("priority", index),
                    enabled=item.get("enabled", True),
                    supports_web_search=item.get("supports_web_search", False),
                    quota_exhausted=item.get("quota_exhausted", False),
                    manual_pause=item.get("manual_pause", False),
                )
            )
        return channels

    def _load_uniapi_override_channel(self) -> Optional[ChannelConfig]:
        if not self._settings.uniapi.api_key or not self._settings.uniapi.base_url:
            return None
        model = (
            self._settings.uniapi.model
            or self._settings.volcengine.model_primary
            or self._settings.dashscope.model
            or self._settings.deepseek.model
            or "gpt-4.1-mini"
        )
        return ChannelConfig(
            id="uniapi-primary",
            name="uniapi-primary",
            provider_type="openai_compatible",
            base_url=_normalize_openai_base_url(self._settings.uniapi.base_url),
            api_key=self._settings.uniapi.api_key,
            model=model,
            priority=1,
            enabled=True,
            supports_web_search=_model_supports_enable_search(model),
            quota_exhausted=False,
            manual_pause=False,
        )

    def _load_legacy_env_channels(self) -> List[Dict[str, Any]]:
        legacy_channels: List[Dict[str, Any]] = []
        if self._settings.uniapi.api_key and self._settings.uniapi.base_url:
            model = (
                self._settings.uniapi.model
                or self._settings.volcengine.model_primary
                or self._settings.dashscope.model
                or self._settings.deepseek.model
                or "gpt-4.1-mini"
            )
            legacy_channels.append(
                {
                    "name": "uniapi-primary",
                    "provider_type": "openai_compatible",
                    "base_url": _normalize_openai_base_url(self._settings.uniapi.base_url),
                    "api_key": self._settings.uniapi.api_key,
                    "model": model,
                    "priority": 1,
                    "supports_web_search": _model_supports_enable_search(model),
                }
            )
        if self._settings.volcengine.api_key:
            legacy_channels.append(
                {
                    "name": "volcengine-primary",
                    "provider_type": "volcengine_search",
                    "base_url": self._settings.volcengine.base_url,
                    "api_key": self._settings.volcengine.api_key,
                    "model": self._settings.volcengine.model_primary,
                    "priority": 10,
                    "supports_web_search": True,
                }
            )
            if self._settings.volcengine.model_fallback:
                legacy_channels.append(
                    {
                        "name": "volcengine-fallback",
                        "provider_type": "volcengine_search",
                        "base_url": self._settings.volcengine.base_url,
                        "api_key": self._settings.volcengine.api_key,
                        "model": self._settings.volcengine.model_fallback,
                        "priority": 11,
                        "supports_web_search": True,
                    }
                )
        if self._settings.dashscope.api_key:
            legacy_channels.append(
                {
                    "name": "dashscope-default",
                    "provider_type": "openai_compatible",
                    "base_url": self._settings.dashscope.base_url,
                    "api_key": self._settings.dashscope.api_key,
                    "model": self._settings.dashscope.model,
                    "priority": 20,
                    "supports_web_search": False,
                }
            )
        if self._settings.deepseek.api_key:
            legacy_channels.append(
                {
                    "name": "deepseek-default",
                    "provider_type": "openai_compatible",
                    "base_url": self._settings.deepseek.base_url,
                    "api_key": self._settings.deepseek.api_key,
                    "model": self._settings.deepseek.model,
                    "priority": 30,
                    "supports_web_search": False,
                }
            )
        return legacy_channels

    def _load_env_fallback_rows(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for index, channel in enumerate(self._load_env_fallback_channels(), start=1):
            items.append(self._channel_to_row(channel, source="env_fallback", order=index))
        return items

    def _channel_to_row(self, channel: ChannelConfig, source: str, order: int) -> Dict[str, Any]:
        return {
            "id": channel.id,
            "name": channel.name,
            "provider_type": channel.provider_type,
            "base_url": channel.base_url,
            "model": channel.model,
            "priority": channel.priority,
            "enabled": channel.enabled,
            "supports_web_search": channel.supports_web_search,
            "quota_exhausted": channel.quota_exhausted,
            "manual_pause": channel.manual_pause,
            "last_error": None,
            "last_checked_at": None,
            "created_at": None,
            "updated_at": None,
            "source": source,
            "readonly": True,
            "masked_api_key": self._mask_api_key(channel.api_key),
            "order": order,
        }

    def _encrypt_api_key(self, api_key: str) -> str:
        if not self._settings.llm_router_secret:
            raise RuntimeError("LLM_ROUTER_SECRET 未配置，无法写入 AI 通道。")
        return encrypt_secret(api_key, self._settings.llm_router_secret)

    @staticmethod
    def _is_database_channel_id(channel_id: str) -> bool:
        try:
            uuid.UUID(str(channel_id))
            return True
        except ValueError:
            return False

    @staticmethod
    def _mask_api_key(api_key: str) -> str:
        if len(api_key) <= 8:
            return "*" * len(api_key)
        return f"{api_key[:4]}***{api_key[-4:]}"


_repository: Optional[ChannelRepository] = None


def get_channel_repository() -> ChannelRepository:
    global _repository
    if _repository is None:
        _repository = ChannelRepository()
    return _repository
