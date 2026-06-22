"""
collector/audit/official_batch_verify.py
针对可高度确定的官方标准链接做保守式批量核验。
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse, unquote

AUTHORITATIVE_HOSTS = {
    "www.etsi.org": "ETSI",
    "etsi.org": "ETSI",
    "www.iec.ch": "IEC",
    "iec.ch": "IEC",
    "eur-lex.europa.eu": "EUR-Lex",
    "www.legislation.gov.uk": "UK legislation",
    "legislation.gov.uk": "UK legislation",
    "csrc.nist.gov": "NIST",
}


def build_official_verification(record: dict) -> Optional[dict]:
    url = (record.get("official_url") or "").strip()
    name = (record.get("name") or "").strip()
    entry_type = (record.get("entry_type") or "").strip()
    if not url or entry_type not in {"standard", "regulation", "certification"}:
        return None

    host = urlparse(url).netloc.lower()
    if host not in AUTHORITATIVE_HOSTS:
        return None

    if host in {"www.etsi.org", "etsi.org"}:
        code = _extract_etsi_code(name)
        if not code:
            return None
        normalized = _normalize_url(url)
        compact = _extract_digits(code)
        if not compact or compact not in normalized.replace("-", ""):
            return None
        return {
            "verified": True,
            "host": host,
            "evidence": f"官方 ETSI 链接与标准号一致: {code}",
        }

    if host in {"www.iec.ch", "iec.ch"}:
        code = _extract_iec_code(name)
        if not code:
            return None
        normalized = _normalize_url(url)
        if code.lower().replace("iec ", "") not in normalized:
            return None
        return {
            "verified": True,
            "host": host,
            "evidence": f"官方 IEC 链接与标准号一致: {code.upper()}",
        }

    if host == "eur-lex.europa.eu":
        celex = _extract_celex(name)
        if celex and celex.lower() in _normalize_url(url):
            return {
                "verified": True,
                "host": host,
                "evidence": f"EUR-Lex 链接包含 CELEX 编号: {celex}",
            }
        act_parts = _extract_eu_act_parts(name)
        normalized = _normalize_url(url)
        if act_parts and all(part in normalized for part in act_parts):
            return {
                "verified": True,
                "host": host,
                "evidence": f"EUR-Lex 链接与法令编号一致: {'/'.join(act_parts)}",
            }
        return None

    if host in {"www.legislation.gov.uk", "legislation.gov.uk"}:
        year_and_number = _extract_ukpga(name)
        if year_and_number and all(part in _normalize_url(url) for part in year_and_number):
            return {
                "verified": True,
                "host": host,
                "evidence": f"UK legislation 链接与法案编号一致: {'/'.join(year_and_number)}",
            }
        return None

    if host == "csrc.nist.gov":
        pub = _extract_nist_pub(name)
        if pub and pub in _normalize_url(url):
            return {
                "verified": True,
                "host": host,
                "evidence": f"NIST 官方链接与出版物编号一致: {pub.upper()}",
            }
        return None

    return None


def _normalize_url(url: str) -> str:
    return unquote(urlparse(url).path.lower())


def _extract_etsi_code(name: str) -> Optional[str]:
    match = re.search(r"\bETSI\s+(EN|TS|TR|GS)\s+(\d{2,6}(?:\s+\d{2,6})*)", name, flags=re.I)
    if not match:
        return None
    prefix = match.group(1).upper()
    digits = re.sub(r"\s+", " ", match.group(2).strip())
    return f"ETSI {prefix} {digits}"


def _extract_iec_code(name: str) -> Optional[str]:
    match = re.search(r"\bIEC\s+(\d{4,6}(?:-\d+)*)", name, flags=re.I)
    return f"iec {match.group(1)}" if match else None


def _extract_celex(name: str) -> Optional[str]:
    match = re.search(r"\bCELEX[:\s]+([0-9A-Z()]+)", name, flags=re.I)
    return match.group(1) if match else None


def _extract_ukpga(name: str) -> Optional[tuple[str, str]]:
    match = re.search(r"\b(\d{4})[^\d]+(\d{1,4})\b", name)
    if not match:
        return None
    return match.group(1), match.group(2)


def _extract_eu_act_parts(name: str) -> Optional[tuple[str, str, str]]:
    match = re.search(r"\b(Regulation|Directive)\s*\(EU\)\s*(\d{4})/(\d{1,5})\b", name, flags=re.I)
    if not match:
        return None
    act_type = "reg" if match.group(1).lower() == "regulation" else "dir"
    return act_type, match.group(2), match.group(3)


def _extract_nist_pub(name: str) -> Optional[str]:
    match = re.search(r"\bSP\s*800[-\s]?(\d+[A-Z\-]*)", name, flags=re.I)
    return f"sp800-{match.group(1).lower()}" if match else None


def _extract_digits(text: str) -> str:
    return "".join(re.findall(r"\d+", text))
