#!/usr/bin/env python3
"""
测试内置 UniAPI/qwen 通道是否支持联网搜索。

用法：
  python scripts/test_uniapi_web_search.py
  python scripts/test_uniapi_web_search.py --model qwen3.6-plus

判定口径：
  1. HTTP 调用成功；
  2. 请求已携带 qwen 的 enable_search=True；
  3. 返回内容包含官方链接或明确的官方来源信息。

注意：这只能证明 UniAPI 兼容站点接受并执行联网搜索参数的概率较高，
最终法规事实仍必须以系统已入库官方原文/官方页面为准。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from openai import OpenAI

from collector.providers.channel_repository import _normalize_openai_base_url
from collector.providers.dashscope import _build_qwen_extra_body
from config.settings import get_settings


def _build_messages() -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是联网搜索连通性测试器。必须先联网检索，再回答。"
                "不要基于记忆作答；如果无法联网，请明确说无法联网。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请联网检索欧盟 Cyber Resilience Act 在 EUR-Lex 的官方页面，"
                "只输出 JSON："
                "{\"can_web_search\": true/false, "
                "\"official_url\": \"官方EUR-Lex链接或null\", "
                "\"full_application_date\": \"全面适用日期YYYY-MM-DD或null\", "
                "\"evidence\": \"一句话说明你看到的官方来源\"}"
            ),
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Test UniAPI qwen web search support.")
    parser.add_argument("--model", help="覆盖 settings.uniapi.model，例如 qwen3.6-plus")
    parser.add_argument("--timeout", type=int, default=90, help="请求超时时间，默认 90 秒")
    parser.add_argument(
        "--trust-env-proxy",
        action="store_true",
        help="继承 HTTP(S)_PROXY/ALL_PROXY 等环境代理；默认关闭，避免本机 SOCKS 依赖影响测试",
    )
    parser.add_argument(
        "--force-search",
        action="store_true",
        help="即使模型名不是 qwen，也强制发送 enable_search=True，用于测试 UniAPI 中转模型是否兼容联网参数",
    )
    parser.add_argument(
        "--forced-search",
        action="store_true",
        help="设置 search_options.forced_search=True，强制模型执行联网搜索",
    )
    parser.add_argument(
        "--search-strategy",
        choices=["turbo", "max", "agent"],
        default="max",
        help="联网搜索量级策略，默认 max；agent 仅适用于部分 qwen3-max 模型",
    )
    parser.add_argument(
        "--enable-source",
        action="store_true",
        help="设置 search_options.enable_source=True，要求返回搜索来源列表（如果网关/模型支持）",
    )
    args = parser.parse_args()

    settings = get_settings()
    api_key = settings.uniapi.api_key
    base_url = _normalize_openai_base_url(settings.uniapi.base_url)
    model = args.model or settings.uniapi.model or "qwen3.6-plus"

    if not api_key or not base_url:
        print("FAIL: UNIAPI_API_KEY 或 UNIAPI_BASE_URL 未配置")
        return 2

    extra_body = _build_qwen_extra_body(model, enable_web_search=True) or {}
    if args.force_search:
        extra_body["enable_search"] = True
    if not extra_body.get("enable_search"):
        print(f"FAIL: 模型 {model} 不是 qwen 系列，脚本不会发送 enable_search；如需强测请加 --force-search")
        return 2
    search_options = {}
    if args.forced_search:
        search_options["forced_search"] = True
    if args.search_strategy:
        search_options["search_strategy"] = args.search_strategy
    if args.enable_source:
        search_options["enable_source"] = True
    if search_options:
        extra_body["search_options"] = search_options

    http_client = httpx.Client(timeout=args.timeout, trust_env=args.trust_env_proxy)
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=args.timeout,
        max_retries=0,
        http_client=http_client,
    )
    started = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=_build_messages(),
            temperature=0.1,
            max_tokens=700,
            extra_body=extra_body,
        )
    except Exception as exc:
        print(f"FAIL: UniAPI 请求失败: {exc}")
        return 1

    content = resp.choices[0].message.content or ""
    elapsed_ms = int((time.time() - started) * 1000)

    print("=== UniAPI Web Search Test ===")
    print(f"base_url: {base_url}")
    print(f"model: {model}")
    print(f"extra_body: {json.dumps(extra_body, ensure_ascii=False)}")
    print(f"latency_ms: {elapsed_ms}")
    if resp.usage:
        print(f"tokens: prompt={resp.usage.prompt_tokens}, completion={resp.usage.completion_tokens}")
    print("=== Response ===")
    print(content.strip())

    lowered = content.lower()
    has_official_link = "eur-lex.europa.eu" in lowered or "europa.eu" in lowered
    has_correct_cra_number = "2024/2847" in lowered or "32024r2847" in lowered
    has_application_date = "2027-12-11" in lowered or "2027年12月11日" in content
    says_no_web = any(token in lowered for token in ("无法联网", "不能联网", "cannot access", "no web access"))

    if has_official_link and has_correct_cra_number and has_application_date and not says_no_web:
        print("PASS: UniAPI 联网搜索参数已发送，返回中包含官方来源和 CRA 全面适用日期。")
        return 0

    print("WARN: 请求成功且已发送 enable_search，但返回不足以确认联网搜索有效或返回来源不精确。")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
