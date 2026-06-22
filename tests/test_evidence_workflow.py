from collector.workflow.evidence_pipeline import EvidencePipelineRunner


def test_weekly_closed_loop_matches_evidence_driven_product_flow():
    calls = []

    runner = EvidencePipelineRunner(
        source_sync=lambda priorities: calls.append(("source_sync", tuple(priorities))) or {"candidate_count": 2},
        artifact_fetch=lambda limit: calls.append(("artifact_fetch", limit)) or {"limit": limit},
        review_bucket=lambda limit: calls.append(("review_bucket", limit)) or {"limit": limit},
        document_parse=lambda limit: calls.append(("document_parse", limit)) or {"limit": limit},
        spec_generate=lambda limit: calls.append(("spec_generate", limit)) or {"limit": limit, "generated": 1},
        read_model_refresh=lambda limit: calls.append(("read_model_refresh", limit)) or {"limit": limit},
        weekly_report=lambda: calls.append(("weekly_report", None)) or {"sent": True},
    )

    result = runner.run_weekly_closed_loop()

    assert calls == [
        ("source_sync", ("P1", "P2", "P3")),
        ("artifact_fetch", 200),
        ("review_bucket", 200),
        ("document_parse", 50),
        ("spec_generate", 10),
        ("read_model_refresh", 500),
        ("weekly_report", None),
    ]
    assert result["knowledge_deposit"]["document_parse"]["limit"] == 50
    assert result["spec_output"]["generated"] == 1
    assert result["query_use"]["read_model_refresh"]["limit"] == 500
    assert result["alerts_and_weekly_report"]["weekly_report"]["sent"] is True
