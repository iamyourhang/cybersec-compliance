import sys
import types
from datetime import timedelta

import scheduler.main as scheduler_main
from database import repository as repository_module
import notifier.alert_scanner as alert_scanner_module


def test_official_source_sync_daily_uses_all_priorities(monkeypatch):
    captured = {}

    class _FakePipeline:
        def sync_country_priorities(self, priorities):
            captured["priorities"] = priorities
            return {"candidate_count": 3}

    monkeypatch.setattr(scheduler_main, "get_official_source_pipeline", lambda: _FakePipeline())

    scheduler_main.job_official_source_sync_daily()

    assert captured["priorities"] == ["P1", "P2", "P3"]


def test_official_source_sync_weekly_uses_p2_p3(monkeypatch):
    captured = {}

    class _FakePipeline:
        def sync_country_priorities(self, priorities):
            captured["priorities"] = priorities
            return {"candidate_count": 5}

    monkeypatch.setattr(scheduler_main, "get_official_source_pipeline", lambda: _FakePipeline())

    scheduler_main.job_official_source_sync_weekly()

    assert captured["priorities"] == ["P2", "P3"]


def test_official_artifact_fetch_uses_pending_ai_and_official_candidates(monkeypatch):
    captured = {"ingested": []}

    monkeypatch.setattr(
        repository_module.SourceRecordRepository,
        "list_pending_artifact_records",
        staticmethod(
            lambda limit=20: [
                {
                    "id": "src-1",
                    "source_status": "candidate",
                    "title": "AI Candidate",
                    "source_url": "https://example.gov/rule",
                    "artifact_url": "https://example.gov/rule.pdf",
                }
            ]
        ),
    )

    class _FakeIngestService:
        def ingest_record(self, item, requested_by="system"):
            captured["ingested"].append((item["id"], requested_by))
            return {"doc_id": "doc-1"}

    monkeypatch.setattr("collector.document.source_ingest.OfficialSourceIngestService", _FakeIngestService)

    result = scheduler_main.job_official_artifact_fetch(limit=1)

    assert result == {"success": 1, "total": 1}
    assert captured["ingested"] == [("src-1", "system:official_source")]


def test_job_document_parse_does_not_write_formal_knowledge(monkeypatch):
    captured = {}

    class _FakeDocRepo:
        @staticmethod
        def list_pending_source_documents(limit=10):
            return [{"id": "doc-1"}]

    monkeypatch.setattr("collector.document.doc_repository.DocRepository.list_pending_source_documents", _FakeDocRepo.list_pending_source_documents)
    monkeypatch.setattr(
        "admin.api.routes.documents._parse_and_index_document",
        lambda doc_id, write_to_knowledge=True: captured.update(
            {"doc_id": doc_id, "write_to_knowledge": write_to_knowledge}
        ),
    )

    scheduler_main.job_document_parse()

    assert captured == {"doc_id": "doc-1", "write_to_knowledge": False}


def test_job_candidate_verification_only_buckets_review_case(monkeypatch):
    calls = {"ensure": 0, "canonical": 0, "index": 0}

    monkeypatch.setattr(
        repository_module.SourceRecordRepository,
        "list_bucketable_records",
        staticmethod(lambda limit=50: [{"id": "src-1", "compliance_id": "rec-1"}]),
    )
    monkeypatch.setattr(
        repository_module.ComplianceRepository,
        "get_by_id",
        staticmethod(
            lambda compliance_id: {
                "id": compliance_id,
                "country_code": "EU",
                "name": "Cyber Resilience Act",
                "entry_type": "regulation",
                "status": "active",
                "authenticity_status": "candidate",
            }
        ),
    )
    monkeypatch.setattr(
        repository_module.ReviewCaseRepository,
        "ensure_for_record",
        staticmethod(lambda record: calls.__setitem__("ensure", calls["ensure"] + 1) or "case-1"),
    )
    monkeypatch.setattr(
        repository_module.CanonicalRequirementRepository,
        "upsert_from_compliance",
        staticmethod(lambda record, verification_status: calls.__setitem__("canonical", calls["canonical"] + 1) or "canon-1"),
    )
    monkeypatch.setattr(
        repository_module.ComplianceIndexRepository,
        "refresh_for_compliance",
        staticmethod(lambda record: calls.__setitem__("index", calls["index"] + 1) or "idx-1"),
    )

    scheduler_main.job_candidate_verification()

    assert calls == {"ensure": 1, "canonical": 1, "index": 1}


def test_weekly_compliance_update_runs_full_evidence_pipeline(monkeypatch):
    calls = []

    class _FakePipeline:
        def sync_country_priorities(self, priorities):
            calls.append(("sync", tuple(priorities)))
            return {"candidate_count": 8}

    monkeypatch.setattr(scheduler_main, "get_official_source_pipeline", lambda: _FakePipeline())
    monkeypatch.setattr(scheduler_main, "job_global_source_registry_refresh", lambda: calls.append(("registry", None)) or {"coverage": {"total": 10}})
    monkeypatch.setattr(scheduler_main, "job_weekly_ai_discovery", lambda limit_countries=scheduler_main.WEEKLY_AI_DISCOVERY_LIMIT_COUNTRIES: calls.append(("ai_discovery", limit_countries)) or {"accepted_count": 2})
    monkeypatch.setattr(scheduler_main, "job_official_artifact_fetch", lambda limit=20: calls.append(("artifact", limit)))
    monkeypatch.setattr(scheduler_main, "job_candidate_verification", lambda limit=50: calls.append(("verify", limit)))
    monkeypatch.setattr(scheduler_main, "job_document_parse", lambda limit=10: calls.append(("parse", limit)))
    monkeypatch.setattr(scheduler_main, "job_spec_generate", lambda limit=10: calls.append(("spec", limit)) or {"generated": 1})
    monkeypatch.setattr(scheduler_main, "job_read_model_refresh", lambda limit=200: calls.append(("refresh", limit)))
    monkeypatch.setattr(scheduler_main, "job_weekly_report", lambda: calls.append(("report", None)) or {"sent": True})

    result = scheduler_main.job_weekly_compliance_update()

    assert calls == [
        ("registry", None),
        ("sync", ("P1", "P2", "P3")),
        ("artifact", 200),
        ("verify", 200),
        ("parse", 50),
        ("spec", 10),
        ("refresh", 500),
        ("report", None),
    ]
    assert result["source_collection"]["official_source_sync"]["candidate_count"] == 8
    assert result["source_collection"]["source_registry_refresh"]["coverage"]["total"] == 10
    assert result["source_collection"]["ai_discovery"]["status"] == "scheduled_separately"
    assert result["source_collection"]["ai_discovery"]["cadence_days"] == 7
    assert result["spec_output"]["generated"] == 1


def test_job_spec_generate_only_processes_verified_indexed_documents(monkeypatch):
    generated = []

    monkeypatch.setattr(
        scheduler_main,
        "_list_verified_documents_needing_specs",
        lambda limit=10: [{"id": "doc-1"}, {"id": "doc-2"}],
    )

    class _FakeSpecGenerator:
        def generate_from_doc(self, doc_id):
            generated.append(doc_id)
            return {"success": True, "spec_count": 3}

    monkeypatch.setattr("collector.document.spec_generator.SpecGeneratorService", _FakeSpecGenerator)

    result = scheduler_main.job_spec_generate(limit=2)

    assert generated == ["doc-1", "doc-2"]
    assert result == {"total": 2, "generated": 2, "failed": 0}


def test_global_source_registry_refresh_seeds_sources_and_coverage(monkeypatch):
    monkeypatch.setattr("scripts.seed_full_country_catalog.seed", lambda: {"inserted": 10, "updated": 199})
    monkeypatch.setattr("scripts.seed_global_official_sources.seed", lambda: (3, 4))
    monkeypatch.setattr("scripts.seed_country_research_outcomes.seed", lambda: 5)
    monkeypatch.setattr("scripts.refresh_country_source_coverage.refresh", lambda: {"total": 120})

    result = scheduler_main.job_global_source_registry_refresh()

    assert result == {
        "country_catalog": {"inserted": 10, "updated": 199},
        "official_sources_inserted": 3,
        "official_sources_updated": 4,
        "research_outcomes_updated": 5,
        "coverage": {"total": 120},
    }


def test_build_scheduler_runs_full_update_every_two_weeks(monkeypatch):
    jobs = {}

    class _FakeJob:
        def __init__(self, job_id, trigger, name):
            self.id = job_id
            self.trigger = trigger
            self.name = name

    class _FakeBlockingScheduler:
        def __init__(self, timezone=None):
            self.timezone = timezone

        def add_job(self, func, trigger, id, name, **kwargs):
            jobs[id] = _FakeJob(id, trigger, name)

        def get_job(self, job_id):
            return jobs.get(job_id)

    class _FakeCronTrigger:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        @classmethod
        def from_crontab(cls, expr, timezone=None):
            return cls(expr, timezone=timezone)

    class _FakeIntervalTrigger:
        def __init__(self, weeks=0, **kwargs):
            self.interval = timedelta(weeks=weeks)
            self.kwargs = kwargs

    monkeypatch_modules = {
        "apscheduler": types.ModuleType("apscheduler"),
        "apscheduler.schedulers": types.ModuleType("apscheduler.schedulers"),
        "apscheduler.schedulers.blocking": types.ModuleType("apscheduler.schedulers.blocking"),
        "apscheduler.triggers": types.ModuleType("apscheduler.triggers"),
        "apscheduler.triggers.cron": types.ModuleType("apscheduler.triggers.cron"),
        "apscheduler.triggers.interval": types.ModuleType("apscheduler.triggers.interval"),
    }
    monkeypatch_modules["apscheduler.schedulers.blocking"].BlockingScheduler = _FakeBlockingScheduler
    monkeypatch_modules["apscheduler.triggers.cron"].CronTrigger = _FakeCronTrigger
    monkeypatch_modules["apscheduler.triggers.interval"].IntervalTrigger = _FakeIntervalTrigger
    for module_name, module in monkeypatch_modules.items():
        monkeypatch.setitem(sys.modules, module_name, module)

    scheduler = scheduler_main.build_scheduler()
    job = scheduler.get_job("weekly_compliance_update")

    assert job.name == "每两周全球合规知识库更新"
    assert job.trigger.interval.days == 14


def test_build_scheduler_does_not_send_frontline_digest_daily(monkeypatch):
    jobs = {}

    class _FakeJob:
        def __init__(self, job_id, trigger, name):
            self.id = job_id
            self.trigger = trigger
            self.name = name

    class _FakeBlockingScheduler:
        def __init__(self, timezone=None):
            self.timezone = timezone

        def add_job(self, func, trigger, id, name, **kwargs):
            jobs[id] = _FakeJob(id, trigger, name)

        def get_job(self, job_id):
            return jobs.get(job_id)

    class _FakeCronTrigger:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        @classmethod
        def from_crontab(cls, expr, timezone=None):
            return cls(expr, timezone=timezone)

    class _FakeIntervalTrigger:
        def __init__(self, weeks=0, **kwargs):
            self.interval = timedelta(weeks=weeks)
            self.kwargs = kwargs

    monkeypatch_modules = {
        "apscheduler": types.ModuleType("apscheduler"),
        "apscheduler.schedulers": types.ModuleType("apscheduler.schedulers"),
        "apscheduler.schedulers.blocking": types.ModuleType("apscheduler.schedulers.blocking"),
        "apscheduler.triggers": types.ModuleType("apscheduler.triggers"),
        "apscheduler.triggers.cron": types.ModuleType("apscheduler.triggers.cron"),
        "apscheduler.triggers.interval": types.ModuleType("apscheduler.triggers.interval"),
    }
    monkeypatch_modules["apscheduler.schedulers.blocking"].BlockingScheduler = _FakeBlockingScheduler
    monkeypatch_modules["apscheduler.triggers.cron"].CronTrigger = _FakeCronTrigger
    monkeypatch_modules["apscheduler.triggers.interval"].IntervalTrigger = _FakeIntervalTrigger
    for module_name, module in monkeypatch_modules.items():
        monkeypatch.setitem(sys.modules, module_name, module)

    scheduler = scheduler_main.build_scheduler()
    job = scheduler.get_job("frontline_feishu_digest")

    assert job is None


def test_job_frontline_feishu_digest_uses_today_ai_collection_window(monkeypatch):
    captured = {}

    class _FakeScanner:
        def scan_frontline_digest(self, **kwargs):
            captured.update(kwargs)
            return 1

    monkeypatch.setattr(scheduler_main, "_hours_since_local_midnight", lambda: 9)
    monkeypatch.setattr(alert_scanner_module, "AlertScanner", lambda: _FakeScanner())

    result = scheduler_main.job_frontline_feishu_digest()

    assert result == {"sent": True, "count": 1}
    assert captured == {"lookback_hours": 9}


def test_job_weekly_ai_discovery_uses_validated_web_search_service(monkeypatch):
    captured = {}

    class _FakeDiscoveryService:
        def run(self, **kwargs):
            captured.update(kwargs)
            return {"status": "success", "candidate_count": 2, "accepted_count": 1}

    monkeypatch.setattr(
        "collector.discovery.service.get_ai_discovery_service",
        lambda: _FakeDiscoveryService(),
    )

    result = scheduler_main.job_weekly_ai_discovery(limit_countries=12)

    assert result["accepted_count"] == 1
    assert captured == {
        "priorities": ["P1", "P2", "P3"],
        "limit_countries": 12,
        "queries_per_country": 6,
        "validation_mode": "ai",
    }


def test_job_key_regulation_countdown_refresh_seeds_cra_milestones(monkeypatch):
    monkeypatch.setattr(
        scheduler_main.ComplianceLifecycleRepository,
        "seed_key_regulation_milestones",
        staticmethod(lambda: {"cra": {"status": "seeded", "milestones": 4}}),
    )

    result = scheduler_main.job_key_regulation_countdown_refresh()

    assert result == {"cra": {"status": "seeded", "milestones": 4}}


def test_build_scheduler_includes_weekly_ai_discovery(monkeypatch):
    jobs = {}

    class _FakeJob:
        def __init__(self, job_id, trigger, name):
            self.id = job_id
            self.trigger = trigger
            self.name = name

    class _FakeBlockingScheduler:
        def __init__(self, timezone=None):
            self.timezone = timezone

        def add_job(self, func, trigger, id, name, **kwargs):
            jobs[id] = _FakeJob(id, trigger, name)

        def get_job(self, job_id):
            return jobs.get(job_id)

    class _FakeCronTrigger:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        @classmethod
        def from_crontab(cls, expr, timezone=None):
            return cls(expr, timezone=timezone)

    class _FakeIntervalTrigger:
        def __init__(self, weeks=0, **kwargs):
            self.interval = timedelta(weeks=weeks)
            self.kwargs = kwargs

    monkeypatch_modules = {
        "apscheduler": types.ModuleType("apscheduler"),
        "apscheduler.schedulers": types.ModuleType("apscheduler.schedulers"),
        "apscheduler.schedulers.blocking": types.ModuleType("apscheduler.schedulers.blocking"),
        "apscheduler.triggers": types.ModuleType("apscheduler.triggers"),
        "apscheduler.triggers.cron": types.ModuleType("apscheduler.triggers.cron"),
        "apscheduler.triggers.interval": types.ModuleType("apscheduler.triggers.interval"),
    }
    monkeypatch_modules["apscheduler.schedulers.blocking"].BlockingScheduler = _FakeBlockingScheduler
    monkeypatch_modules["apscheduler.triggers.cron"].CronTrigger = _FakeCronTrigger
    monkeypatch_modules["apscheduler.triggers.interval"].IntervalTrigger = _FakeIntervalTrigger
    for module_name, module in monkeypatch_modules.items():
        monkeypatch.setitem(sys.modules, module_name, module)

    scheduler = scheduler_main.build_scheduler()
    job = scheduler.get_job("weekly_ai_discovery")

    assert job.name == "每周AI官方候选发现"
    assert job.trigger.args == ("30 0 * * 1",)


def test_build_scheduler_includes_key_regulation_countdown_refresh(monkeypatch):
    jobs = {}

    class _FakeJob:
        def __init__(self, job_id, trigger, name):
            self.id = job_id
            self.trigger = trigger
            self.name = name

    class _FakeBlockingScheduler:
        def __init__(self, timezone=None):
            self.timezone = timezone

        def add_job(self, func, trigger, id, name, **kwargs):
            jobs[id] = _FakeJob(id, trigger, name)

        def get_job(self, job_id):
            return jobs.get(job_id)

    class _FakeCronTrigger:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        @classmethod
        def from_crontab(cls, expr, timezone=None):
            return cls(expr, timezone=timezone)

    class _FakeIntervalTrigger:
        def __init__(self, weeks=0, **kwargs):
            self.interval = timedelta(weeks=weeks)
            self.kwargs = kwargs

    monkeypatch_modules = {
        "apscheduler": types.ModuleType("apscheduler"),
        "apscheduler.schedulers": types.ModuleType("apscheduler.schedulers"),
        "apscheduler.schedulers.blocking": types.ModuleType("apscheduler.schedulers.blocking"),
        "apscheduler.triggers": types.ModuleType("apscheduler.triggers"),
        "apscheduler.triggers.cron": types.ModuleType("apscheduler.triggers.cron"),
        "apscheduler.triggers.interval": types.ModuleType("apscheduler.triggers.interval"),
    }
    monkeypatch_modules["apscheduler.schedulers.blocking"].BlockingScheduler = _FakeBlockingScheduler
    monkeypatch_modules["apscheduler.triggers.cron"].CronTrigger = _FakeCronTrigger
    monkeypatch_modules["apscheduler.triggers.interval"].IntervalTrigger = _FakeIntervalTrigger
    for module_name, module in monkeypatch_modules.items():
        monkeypatch.setitem(sys.modules, module_name, module)

    scheduler = scheduler_main.build_scheduler()
    job = scheduler.get_job("key_regulation_countdown_refresh")

    assert job.name == "关键法规适用节点倒计时刷新"
    assert job.trigger.args == ("5 0 * * *",)
