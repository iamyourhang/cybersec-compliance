import scheduler.main as scheduler_main


class _FakeCursor:
    def __init__(self):
        self.sqls = []

    def execute(self, sql, params=None):
        self.sqls.append(sql)
        self._last_sql = sql

    def fetchone(self):
        sql = self._last_sql
        if "COUNT(*) AS total" in sql:
            return {"total": 100}
        if "COUNT(DISTINCT country_code) AS cnt" in sql:
            return {"cnt": 12}
        if "FROM source_records" in sql:
            return {"cnt": 7}
        if "FROM review_cases" in sql and "current_status='verified'" in sql:
            return {"cnt": 25}
        if "FROM review_cases" in sql and "current_status='quarantined'" in sql:
            return {"cnt": 3}
        if "FROM source_artifacts" in sql:
            return {"cnt": 9}
        raise AssertionError(f"unexpected fetchone SQL: {sql}")

    def fetchall(self):
        if "FROM compliance_index ci" in self._last_sql:
            return [{"name": "CRA", "country_name": "欧盟", "days_until_effective": 10}]
        return []


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_collect_weekly_report_stats(monkeypatch):
    fake_cursor = _FakeCursor()
    monkeypatch.setattr(scheduler_main, "get_cursor", lambda: _CursorContext(fake_cursor))
    monkeypatch.setattr(
        scheduler_main.ComplianceLifecycleRepository,
        "get_upcoming_milestones",
        lambda days, limit: [{"name": "CRA", "country_name": "欧盟", "days_until_effective": 10}],
    )

    stats = scheduler_main._collect_weekly_report_stats()

    assert stats["total_records"] == 100
    assert stats["country_count"] == 12
    assert stats["candidate_this_week"] == 7
    assert stats["verified_this_week"] == 25
    assert stats["quarantined_this_week"] == 3
    assert stats["source_artifacts_this_week"] == 9
    assert stats["upcoming_alerts"][0]["name"] == "CRA"


def test_collect_weekly_report_stats_uses_verified_30_day_window(monkeypatch):
    fake_cursor = _FakeCursor()
    captured = {}
    monkeypatch.setattr(scheduler_main, "get_cursor", lambda: _CursorContext(fake_cursor))
    monkeypatch.setattr(
        scheduler_main.ComplianceLifecycleRepository,
        "get_upcoming_milestones",
        lambda **kwargs: captured.update(kwargs) or [],
    )

    scheduler_main._collect_weekly_report_stats()

    assert captured == {"days": 30, "limit": 10}
