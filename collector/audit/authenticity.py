"""
collector/audit/authenticity.py
法规/认证真实性审计：基于确定性规则做风险评分，并可选探测官方链接。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

import re

TEMPLATE_NAME_RE = re.compile(
    r"(?i)(national cybersecurity certification scheme|voluntary cybersecurity|"
    r"cybersecurity label|cybersecurity certification scheme|certification framework|"
    r"network equipment cybersecurity certification)"
)
GENERIC_OFFICIAL_PATH_RE = re.compile(
    r"(?i)(/search|/standards-search|/certification$|/certifications$|/regulations$|/policies$)"
)
AI_SOURCE_RE = re.compile(r"(?i)(volcengine|dashscope|deepseek|doubao|qwen|openai)")


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    status_code: Optional[int]
    final_url: Optional[str]
    error: Optional[str]


def assess_record_authenticity(record: Dict[str, Any], probe: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    reasons: List[str] = []
    score = 0

    name = str(record.get("name") or "").strip()
    entry_type = str(record.get("entry_type") or "").strip().lower()
    official_url = str(record.get("official_url") or "").strip() or None
    verified = bool(record.get("verified"))
    confidence = int(record.get("confidence_score") or 0)
    data_source = str(record.get("data_source") or "").strip()

    if not official_url:
        score += 25
        reasons.append("missing_official_url")
    else:
        parsed = urlparse(official_url)
        if not parsed.scheme.startswith("http") or not parsed.netloc:
            score += 25
            reasons.append("invalid_official_url")
        if GENERIC_OFFICIAL_PATH_RE.search(parsed.path or ""):
            score += 10
            reasons.append("generic_official_url")

    if not verified:
        score += 10
        reasons.append("not_human_verified")

    if confidence < 70:
        score += 20
        reasons.append("low_confidence_score")
    elif confidence < 85:
        score += 10
        reasons.append("medium_confidence_score")

    if TEMPLATE_NAME_RE.search(name):
        score += 20
        reasons.append("template_like_name")

    if entry_type == "certification" and any(token in name.lower() for token in ["scheme", "label", "framework", "mark"]):
        score += 10
        reasons.append("scheme_like_certification_name")

    if AI_SOURCE_RE.search(data_source) and not verified:
        score += 10
        reasons.append("ai_generated_unverified")

    if probe:
        probe_verdict = classify_probe_result(probe)
        if probe_verdict["reason"]:
            reasons.append(probe_verdict["reason"])
        score += probe_verdict["risk_delta"]

    score = min(score, 100)
    if score >= 80:
        level = "critical"
        action = "quarantine"
    elif score >= 60:
        level = "high"
        action = "review"
    elif score >= 30:
        level = "medium"
        action = "review"
    else:
        level = "low"
        action = "keep"

    return {
        "risk_score": score,
        "risk_level": level,
        "reasons": reasons,
        "recommended_action": action,
    }


def probe_official_url(url: str, timeout: int = 20) -> Dict[str, Any]:
    opener = build_opener(HTTPRedirectHandler)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        response = opener.open(request, timeout=timeout)
        return {
            "ok": 200 <= response.status < 400,
            "status_code": response.status,
            "final_url": response.geturl(),
            "error": None,
        }
    except HTTPError as exc:
        return {
            "ok": False,
            "status_code": exc.code,
            "final_url": exc.geturl(),
            "error": None,
        }
    except (URLError, TimeoutError) as exc:
        return {
            "ok": False,
            "status_code": None,
            "final_url": None,
            "error": str(exc),
        }


def classify_probe_result(probe: Dict[str, Any]) -> Dict[str, Any]:
    status_code = probe.get("status_code")
    error = probe.get("error")
    final_url = str(probe.get("final_url") or "")

    if error:
        return {"risk_delta": 35, "reason": "official_url_unreachable"}
    if status_code == 404:
        return {"risk_delta": 40, "reason": "official_url_not_found"}
    if status_code is not None and status_code >= 500:
        return {"risk_delta": 20, "reason": "official_url_server_error"}
    if status_code == 403:
        return {"risk_delta": 5, "reason": "official_url_forbidden"}
    if final_url and _looks_like_homepage(final_url):
        return {"risk_delta": 15, "reason": "official_url_redirected_to_home"}
    return {"risk_delta": 0, "reason": None}


def _looks_like_homepage(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/")
    return path in {"", "/"} or path.lower() in {"/en", "/home", "/index", "/index.html"}
