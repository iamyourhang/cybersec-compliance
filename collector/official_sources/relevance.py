from __future__ import annotations

import re


CYBER_RELEVANCE_PATTERNS = [
    r"\bcyber\s*security\b",
    r"\bcybersecurity\b",
    r"\bcyber\s*resilience\b",
    r"\bsecurity\s+standards?\s+for\s+smart\s+devices?\b",
    r"\binternet\s+of\s+things\b",
    r"\biot\b.*\bsecurity\b",
    r"\bsecurity\b.*\biot\b",
    r"\bcritical\s+infrastructure\b",
    r"\bnetwork\s+and\s+information\s+systems?\b",
    r"\bnis2?\b",
    r"\bcommon\s+criteria\b",
    r"\bit\s+security\s+label\b",
    r"\bcyber\s+trust\s+mark\b",
    r"\bcert-in\b",
    r"\binformation\s+security\b",
    r"\bcloud\s+security\b",
    r"정보보호",
    r"보안인증",
    r"物聯網.*資安",
    r"資安.*驗證",
    r"ciberseguridad",
    r"segurança\s+cibernética",
    r"cybersécurité",
]

NON_CYBER_OUT_OF_SCOPE_PATTERNS = [
    r"\belectromagnetic\b",
    r"\bemc\b",
    r"\bspectrum\b",
    r"\bradio\s+(equipment|communication|frequency)\b",
    r"\bbroadcast\b",
    r"\btype[-\s]?approval\b",
    r"\btype[-\s]?approved\b",
    r"\btelecom\s+equipment\b",
    r"\bequipment\s+conformity\b",
    r"\bwireless\s+equipment\b",
    r"\btechnical\s+standards?\b",
    r"\bhomologation\b",
]


def is_cybersecurity_relevant(text: str) -> bool:
    """Return True for cybersecurity scope, false for official-but-non-cyber noise."""
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not normalized:
        return False
    has_cyber_signal = any(re.search(pattern, normalized, re.I) for pattern in CYBER_RELEVANCE_PATTERNS)
    has_non_cyber_noise = any(re.search(pattern, normalized, re.I) for pattern in NON_CYBER_OUT_OF_SCOPE_PATTERNS)
    if has_non_cyber_noise and not has_cyber_signal:
        return False
    return has_cyber_signal or not has_non_cyber_noise
