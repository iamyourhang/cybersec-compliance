from __future__ import annotations

import json
from typing import Any, Optional

from collector.parsers.compliance_parser import extract_json_from_text
from collector.parsers.prompts import build_official_source_fallback_prompt, get_system_prompt
from collector.providers.channel_router import ChannelRouter, get_channel_router


class OfficialSourceFallbackSearcher:
    def __init__(self, router: Optional[ChannelRouter] = None):
        self._router = router or get_channel_router()

    def search(self, source: dict[str, Any], error_message: str | None = None) -> list[dict[str, Any]]:
        prompt = build_official_source_fallback_prompt(source, fetch_error=error_message)
        response = self._router.chat(
            messages=[
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2500,
            enable_web_search=True,
        )
        payload = json.loads(extract_json_from_text(response.content))
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            return []
        return [self._normalize_item(item) for item in payload if isinstance(item, dict)]

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": (item.get("title") or "").strip(),
            "detail_url": (item.get("detail_url") or "").strip(),
            "artifact_url": (item.get("artifact_url") or "").strip() or None,
            "published_date": item.get("published_date"),
            "summary": (item.get("summary") or "").strip() or None,
            "issuing_body": (item.get("issuing_body") or "").strip() or None,
            "entry_type": (item.get("entry_type") or "").strip() or None,
            "why_official": (item.get("why_official") or "").strip() or None,
        }
