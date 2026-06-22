"""
collector/providers/router_models.py
LLM 通道路由相关数据模型。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChannelConfig:
    id: str
    name: str
    provider_type: str
    base_url: str
    api_key: str
    model: str
    priority: int
    enabled: bool
    supports_web_search: bool
    quota_exhausted: bool
    manual_pause: bool


class QuotaExhaustedError(RuntimeError):
    """仅表示额度耗尽，可触发自动切换。"""
