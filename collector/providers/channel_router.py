"""
collector/providers/channel_router.py
统一 LLM 通道路由器。
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from collector.providers.base import BaseProvider, LLMResponse
from collector.providers.channel_repository import ChannelRepository, get_channel_repository
from collector.providers.factory import build_provider_from_channel
from collector.providers.router_models import ChannelConfig, QuotaExhaustedError

logger = logging.getLogger(__name__)


class ChannelRouter:
    def __init__(
        self,
        repository: Optional[ChannelRepository] = None,
        adapter_factory: Optional[Callable[[ChannelConfig], BaseProvider]] = None,
    ):
        self._repository = repository or get_channel_repository()
        self._adapter_factory = adapter_factory or build_provider_from_channel

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        enable_web_search: bool = False,
        **kwargs,
    ) -> LLMResponse:
        candidates = sorted(
            self._repository.list_routable_channels(),
            key=lambda channel: channel.priority,
        )
        last_error: Optional[Exception] = None
        for channel in candidates:
            if not channel.enabled or channel.manual_pause or channel.quota_exhausted:
                continue
            try:
                provider = self._adapter_factory(channel)
                return provider.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    enable_web_search=enable_web_search and channel.supports_web_search,
                    **kwargs,
                )
            except QuotaExhaustedError as exc:
                logger.warning("通道额度耗尽，切换下一个 [%s]: %s", channel.name, exc)
                self._repository.mark_quota_exhausted(channel.id, str(exc))
                self._repository.add_event(
                    channel.id,
                    "quota_exhausted_detected",
                    str(exc),
                    str(exc),
                )
                last_error = exc
                continue

        raise RuntimeError(
            "当前无可用 AI 通道，请在后台检查额度或恢复被暂停通道。"
        ) from last_error


_router: Optional[ChannelRouter] = None


def get_channel_router() -> ChannelRouter:
    global _router
    if _router is None:
        _router = ChannelRouter()
    return _router
