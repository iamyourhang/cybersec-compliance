from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class DiscoveredItem:
    title: str
    detail_url: str
    published_date: Optional[str] = None
    artifact_url: Optional[str] = None
    summary: Optional[str] = None
    issuing_body: Optional[str] = None
    entry_type: Optional[str] = None


@dataclass
class SyncStats:
    source_id: str
    discovered_count: int = 0
    candidate_count: int = 0
    artifact_count: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "discovered_count": self.discovered_count,
            "candidate_count": self.candidate_count,
            "artifact_count": self.artifact_count,
        }
