"""
collector/providers/base.py
AI Provider 抽象基类 + 多模型自动降级管理器
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """单个 Provider 的配置"""
    name: str                        # 标识符，如 volcengine_primary
    provider_type: str               # volcengine / dashscope / deepseek
    api_key: str
    base_url: str
    model: str
    timeout: int = 120
    max_retries: int = 3
    priority: int = 1                # 数字越小越优先
    supports_web_search: bool = False


@dataclass
class LLMResponse:
    """统一的 LLM 响应格式"""
    content: str
    provider_name: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    web_search_used: bool = False


class BaseProvider(ABC):
    """AI Provider 抽象基类"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{config.name}")

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        enable_web_search: bool = False,
        **kwargs,
    ) -> LLMResponse:
        """发送对话请求，返回统一格式响应"""
        ...

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def supports_web_search(self) -> bool:
        return self.config.supports_web_search


class ProviderManager:
    """
    多模型自动降级管理器。
    按优先级依次尝试各 Provider，任一成功则返回。
    """

    def __init__(self, providers: List[BaseProvider]):
        # 按 priority 升序排列（数字小=优先）
        self._providers = sorted(providers, key=lambda p: p.config.priority)
        logger.info(
            "ProviderManager 初始化，Provider 顺序: %s",
            " → ".join(p.name for p in self._providers),
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        enable_web_search: bool = False,
        require_web_search: bool = False,
        **kwargs,
    ) -> LLMResponse:
        """
        发送对话，自动降级。
        require_web_search=True 时，跳过不支持联网搜索的 Provider。
        """
        candidates = self._providers
        if require_web_search:
            candidates = [p for p in self._providers if p.supports_web_search]
            if not candidates:
                raise RuntimeError("没有支持联网搜索的 Provider 可用")

        last_error: Optional[Exception] = None
        for provider in candidates:
            try:
                logger.info("🤖 使用 Provider: %s [%s]", provider.name, provider.config.model)
                resp = provider.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    enable_web_search=enable_web_search and provider.supports_web_search,
                    **kwargs,
                )
                logger.info(
                    "✅ %s 响应成功 [tokens=%d/%d, latency=%.1fms]",
                    provider.name,
                    resp.prompt_tokens,
                    resp.completion_tokens,
                    resp.latency_ms,
                )
                return resp
            except Exception as e:
                logger.warning("⚠️  Provider %s 失败: %s，尝试下一个", provider.name, e)
                last_error = e
                time.sleep(1)  # 降级前短暂等待

        raise RuntimeError(
            f"所有 Provider 均失败，最后错误: {last_error}"
        ) from last_error

    def get_provider_names(self) -> List[str]:
        return [p.name for p in self._providers]
