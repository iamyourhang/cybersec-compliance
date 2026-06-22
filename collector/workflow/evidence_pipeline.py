"""
Evidence-driven product workflow.

This module is the code-level contract for the product flow:
official collection -> evidence review -> corpus deposit -> spec output ->
query use -> alerts/weekly report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable


SyncFunc = Callable[[Iterable[str]], Dict[str, Any]]
LimitFunc = Callable[[int], Dict[str, Any] | None]
ReportFunc = Callable[[], Dict[str, Any] | None]


@dataclass
class EvidencePipelineRunner:
    source_sync: SyncFunc
    artifact_fetch: LimitFunc
    review_bucket: LimitFunc
    document_parse: LimitFunc
    spec_generate: LimitFunc
    read_model_refresh: LimitFunc
    weekly_report: ReportFunc

    def run_weekly_closed_loop(
        self,
        artifact_limit: int = 200,
        review_limit: int = 200,
        parse_limit: int = 50,
        spec_limit: int = 10,
        refresh_limit: int = 500,
    ) -> Dict[str, Any]:
        source_result = self.source_sync(["P1", "P2", "P3"])
        artifact_result = self.artifact_fetch(artifact_limit) or {"limit": artifact_limit}
        review_result = self.review_bucket(review_limit) or {"limit": review_limit}
        parse_result = self.document_parse(parse_limit) or {"limit": parse_limit}
        spec_result = self.spec_generate(spec_limit) or {"limit": spec_limit}
        refresh_result = self.read_model_refresh(refresh_limit) or {"limit": refresh_limit}
        report_result = self.weekly_report() or {"sent": True}

        return {
            "source_collection": {
                "official_source_sync": source_result,
                "artifact_fetch": artifact_result,
            },
            "evidence_review": {
                "review_bucket": review_result,
            },
            "knowledge_deposit": {
                "document_parse": parse_result,
            },
            "spec_output": spec_result,
            "query_use": {
                "read_model_refresh": refresh_result,
            },
            "alerts_and_weekly_report": {
                "weekly_report": report_result,
            },
        }
