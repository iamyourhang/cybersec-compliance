from datetime import date


class _FakeCursor:
    def __init__(self):
        self.executed_sql = ""
        self.executed_params = None

    def execute(self, sql, params=None):
        self.executed_sql = sql
        self.executed_params = params

    def fetchall(self):
        return [
            {
                "id": "rec-1",
                "name": "Cyber Resilience Act",
                "entry_type": "regulation",
                "country_code": "EU",
                "country_name": "欧盟",
                "priority": 1,
                "milestone_key": "reporting_obligations_apply",
                "milestone_label_zh": "漏洞与严重事件报告义务开始适用",
                "effective_date": date(2026, 9, 11),
                "milestone_date": date(2026, 9, 11),
                "days_until_effective": 122,
                "mandatory": "mandatory",
                "applicable_products": ["router"],
            }
        ]


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_feishu_upcoming_uses_verified_read_model(monkeypatch):
    from feishu_bot.query_handler import query_upcoming

    fake_cursor = _FakeCursor()
    captured = {}

    def _fake_upcoming(**kwargs):
        captured.update(kwargs)
        return fake_cursor.fetchall()

    monkeypatch.setattr(
        "feishu_bot.query_handler.ComplianceLifecycleRepository.get_upcoming_milestones",
        _fake_upcoming,
    )

    rows = query_upcoming(days=180)

    assert rows[0]["effective_date"] == "2026-09-11"
    assert rows[0]["milestone_date"] == "2026-09-11"
    assert rows[0]["milestone_label_zh"] == "漏洞与严重事件报告义务开始适用"
    assert captured == {"days": 180, "limit": 20}
