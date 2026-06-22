"""
collector/providers/volcengine.py
火山引擎 doubao 系列模型 Provider（主力，支持联网搜索）

doubao-seed-2.0-pro 联网搜索 API 文档：
https://www.volcengine.com/docs/82379/1399930
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI, APIError, APITimeoutError, RateLimitError

from collector.providers.base import BaseProvider, LLMResponse, ProviderConfig
from collector.providers.router_models import QuotaExhaustedError

logger = logging.getLogger(__name__)


def _is_quota_exhausted_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "insufficient_quota",
            "quota exceeded",
            "exceeded your current quota",
            "insufficient balance",
            "balance not enough",
            "余额不足",
            "额度已用完",
        )
    )


class VolcengineProvider(BaseProvider):
    """
    火山引擎 doubao 模型 Provider。
    doubao-seed-2.0-pro 支持联网搜索，通过 extra_body 传入搜索配置。
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=0,  # 由 ProviderManager 控制重试
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        enable_web_search: bool = True,
        search_recency_filter: str = "month",   # day/week/month/year
        **kwargs,
    ) -> LLMResponse:
        """
        调用 doubao 模型。
        enable_web_search=True 时通过 extra_body 开启联网搜索。
        """
        extra_body: Dict[str, Any] = {}
        if enable_web_search and self.config.supports_web_search:
            # doubao-seed-2.0-pro 联网搜索参数
            extra_body["search_config"] = {
                "search_strategy": "auto",           # auto 自动判断是否需要搜索
                "time_range": search_recency_filter, # 搜索时间范围
                "enable_citation": True,             # 返回引用来源
            }
            logger.debug("联网搜索已启用 [recency=%s]", search_recency_filter)

        attempt = 0
        last_error: Optional[Exception] = None

        while attempt < self.config.max_retries:
            attempt += 1
            t0 = time.time()
            try:
                resp = self._client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_body=extra_body if extra_body else None,
                    **{k: v for k, v in kwargs.items()
                       if k not in ("enable_web_search", "search_recency_filter")},
                )
                latency = (time.time() - t0) * 1000
                content = resp.choices[0].message.content or ""

                return LLMResponse(
                    content=content,
                    provider_name=self.config.name,
                    model=self.config.model,
                    prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                    completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
                    latency_ms=latency,
                    web_search_used=enable_web_search and bool(extra_body),
                )

            except RateLimitError as e:
                wait = 60 * attempt
                logger.warning("限流，%ds后重试（第%d次）: %s", wait, attempt, e)
                time.sleep(wait)
                last_error = e

            except APITimeoutError as e:
                logger.warning("超时，重试（第%d次）", attempt)
                time.sleep(5 * attempt)
                last_error = e

            except APIError as e:
                if _is_quota_exhausted_error(e):
                    raise QuotaExhaustedError(str(e)) from e
                # 4xx 错误不重试
                if hasattr(e, "status_code") and e.status_code and e.status_code < 500:
                    logger.error("API 客户端错误 %s: %s", e.status_code, e)
                    raise
                logger.warning("API 服务端错误，重试（第%d次）: %s", attempt, e)
                time.sleep(10 * attempt)
                last_error = e

        raise RuntimeError(
            f"Volcengine Provider 重试{self.config.max_retries}次后仍失败"
        ) from last_error


def create_volcengine_providers(
    api_key: str,
    base_url: str = None,
    primary_model: str = None,
    fallback_model: str = None,
) -> List[VolcengineProvider]:
    """工厂函数：创建火山引擎主力 + 备用 Provider"""
    return [
        VolcengineProvider(ProviderConfig(
            name="volcengine_primary",
            provider_type="volcengine",
            api_key=api_key,
            base_url=base_url,
            model=primary_model,
            priority=1,
            supports_web_search=True,
            timeout=180,
            max_retries=3,
        )),
        VolcengineProvider(ProviderConfig(
            name="volcengine_fallback",
            provider_type="volcengine",
            api_key=api_key,
            base_url=base_url,
            model=fallback_model,
            priority=2,
            supports_web_search=True,
            timeout=120,
            max_retries=2,
        )),
    ]
