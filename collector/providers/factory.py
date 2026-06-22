"""
collector/providers/factory.py
根据 settings.py 配置自动组装 ProviderManager，含可用性检测。
同时提供按通道定义动态构造适配器的能力。
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

from collector.providers.base import BaseProvider, ProviderManager
from collector.providers.volcengine import VolcengineProvider, create_volcengine_providers
from collector.providers.dashscope import create_dashscope_provider, create_deepseek_provider
from collector.providers.dashscope import OpenAICompatProvider
from collector.providers.router_models import ChannelConfig
from collector.providers.base import ProviderConfig
from config.settings import get_settings

logger = logging.getLogger(__name__)


def _normalize_openai_base_url(base_url: str) -> str:
    parsed = urlparse((base_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return base_url
    path = (parsed.path or "").rstrip("/")
    if path:
        return base_url.rstrip("/")
    return f"{base_url.rstrip('/')}/v1"


def build_provider_manager() -> ProviderManager:
    """
    根据 .env 配置构建 ProviderManager。
    有 API Key 的 Provider 才会被加入。
    至少需要一个可用 Provider，否则抛出异常。
    """
    settings = get_settings()
    providers: list[BaseProvider] = []

    if settings.uniapi.api_key and settings.uniapi.base_url:
        providers.append(
            OpenAICompatProvider(
                ProviderConfig(
                    name="uniapi_primary",
                    provider_type="openai_compatible",
                    api_key=settings.uniapi.api_key,
                    base_url=_normalize_openai_base_url(settings.uniapi.base_url),
                    model=(
                        settings.uniapi.model
                        or settings.volcengine.model_primary
                        or settings.dashscope.model
                        or settings.deepseek.model
                        or "gpt-4.1-mini"
                    ),
                    priority=1,
                    supports_web_search=False,
                    timeout=120,
                    max_retries=2,
                )
            )
        )
        logger.info("✅ UniAPI Provider 已加载: %s", settings.uniapi.model or settings.volcengine.model_primary or settings.dashscope.model or settings.deepseek.model or "gpt-4.1-mini")

    # 火山引擎（主力）
    if settings.volcengine.api_key:
        volcengine_list = create_volcengine_providers(
            api_key=settings.volcengine.api_key,
            base_url=settings.volcengine.base_url,
            primary_model=settings.volcengine.model_primary,
            fallback_model=settings.volcengine.model_fallback,
        )
        providers.extend(volcengine_list)
        logger.info("✅ 火山引擎 Provider 已加载: %s / %s",
                    settings.volcengine.model_primary,
                    settings.volcengine.model_fallback)
    else:
        logger.warning("⚠️  火山引擎 API Key 未配置，跳过")

    # 阿里百炼（备用）
    if settings.dashscope.api_key:
        providers.append(create_dashscope_provider(
            api_key=settings.dashscope.api_key,
            model=settings.dashscope.model,
        ))
        logger.info("✅ 阿里百炼 Provider 已加载: %s", settings.dashscope.model)
    else:
        logger.info("ℹ️  阿里百炼 API Key 未配置，跳过")

    # DeepSeek（备用）
    if settings.deepseek.api_key:
        providers.append(create_deepseek_provider(api_key=settings.deepseek.api_key))
        logger.info("✅ DeepSeek Provider 已加载")
    else:
        logger.info("ℹ️  DeepSeek API Key 未配置，跳过")

    if not providers:
        raise RuntimeError(
            "❌ 没有可用的 AI Provider！请在 config/.env 中配置至少一个 API Key。"
        )

    logger.info("📦 共加载 %d 个 Provider", len(providers))
    return ProviderManager(providers)


# 模块级单例（懒加载）
_manager: Optional[ProviderManager] = None


def get_provider_manager() -> ProviderManager:
    """获取全局 ProviderManager 单例"""
    global _manager
    if _manager is None:
        _manager = build_provider_manager()
    return _manager


def build_provider_from_channel(channel: ChannelConfig) -> BaseProvider:
    config = ProviderConfig(
        name=channel.name,
        provider_type=channel.provider_type,
        api_key=channel.api_key,
        base_url=channel.base_url,
        model=channel.model,
        priority=channel.priority,
        supports_web_search=channel.supports_web_search,
    )
    if channel.provider_type == "volcengine_search":
        return VolcengineProvider(config)
    return OpenAICompatProvider(config)
