"""
collector/providers/dashscope.py  (兼容 DeepSeek)
阿里百炼 qwen-max + DeepSeek 备用 Provider
两者都兼容 OpenAI 接口，共用同一个实现类
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from openai import OpenAI, APIError, APITimeoutError, RateLimitError

from collector.providers.base import BaseProvider, LLMResponse, ProviderConfig
from collector.providers.router_models import QuotaExhaustedError

logger = logging.getLogger(__name__)


def _build_qwen_extra_body(model: str, enable_web_search: bool) -> Optional[Dict[str, object]]:
    lowered = (model or "").lower()
    extra_body: Dict[str, object] = {}
    if enable_web_search and _supports_enable_search(lowered):
        extra_body["enable_search"] = True
        extra_body["search_options"] = {
            "forced_search": True,
            "search_strategy": "max",
            "enable_source": True,
        }
    if "qwen3" in lowered:
        # JSON extraction tasks should avoid long chain-of-thought style latency.
        extra_body["enable_thinking"] = False
    return extra_body or None


def _supports_enable_search(lowered_model: str) -> bool:
    if "qwen" in lowered_model:
        return True
    # UniAPI 透传实测：deepseek-v4-flash 支持 enable_search；
    # deepseek-v4-pro 在同一参数下不稳定，暂不作为联网发现通道。
    return lowered_model == "deepseek-v4-flash"


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


class OpenAICompatProvider(BaseProvider):
    """
    OpenAI 接口兼容 Provider。
    适用于阿里百炼（DashScope）、DeepSeek 等兼容 OpenAI 协议的服务。
    这些服务不支持 doubao 特有的联网搜索 extra_body，但 qwen-max 有自己的搜索参数。
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=0,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        enable_web_search: bool = False,
        **kwargs,
    ) -> LLMResponse:
        attempt = 0
        last_error: Optional[Exception] = None
        max_attempts = int(kwargs.get("max_retries", self.config.max_retries) or self.config.max_retries)
        request_timeout = kwargs.get("timeout")

        # qwen 系列支持通过 extra_body 开启联网搜索；qwen3 默认关闭思考以稳定结构化抽取。
        extra_body = _build_qwen_extra_body(self.config.model, enable_web_search)

        while attempt < max_attempts:
            attempt += 1
            t0 = time.time()
            try:
                create_kwargs = dict(
                    model=self.config.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if extra_body:
                    create_kwargs["extra_body"] = extra_body
                if request_timeout:
                    create_kwargs["timeout"] = request_timeout

                resp = self._client.chat.completions.create(**create_kwargs)
                latency = (time.time() - t0) * 1000
                content = resp.choices[0].message.content or ""

                return LLMResponse(
                    content=content,
                    provider_name=self.config.name,
                    model=self.config.model,
                    prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                    completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
                    latency_ms=latency,
                    web_search_used=bool(extra_body),
                )

            except RateLimitError as e:
                wait = 30 * attempt
                logger.warning("[%s] 限流，%ds后重试: %s", self.config.name, wait, e)
                time.sleep(wait)
                last_error = e

            except APITimeoutError as e:
                logger.warning("[%s] 超时，重试（第%d次）", self.config.name, attempt)
                time.sleep(5 * attempt)
                last_error = e

            except APIError as e:
                if _is_quota_exhausted_error(e):
                    raise QuotaExhaustedError(str(e)) from e
                if hasattr(e, "status_code") and e.status_code and e.status_code < 500:
                    raise
                logger.warning("[%s] 服务端错误，重试: %s", self.config.name, e)
                time.sleep(10 * attempt)
                last_error = e

        raise RuntimeError(
            f"[{self.config.name}] 重试{max_attempts}次后仍失败"
        ) from last_error


def create_dashscope_provider(api_key: str, model: str = "qwen-max") -> OpenAICompatProvider:
    return OpenAICompatProvider(ProviderConfig(
        name="dashscope_qwen",
        provider_type="dashscope",
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model=model,
        priority=3,
        supports_web_search=True,  # qwen 支持 enable_search
        timeout=120,
        max_retries=2,
    ))


def create_deepseek_provider(api_key: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(ProviderConfig(
        name="deepseek_chat",
        provider_type="deepseek",
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        priority=4,
        supports_web_search=False,
        timeout=120,
        max_retries=2,
    ))
