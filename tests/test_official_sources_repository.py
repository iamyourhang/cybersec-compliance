from collector.official_sources import repository as repository_module
from collector.official_sources.repository import OfficialSourceRepository


class _FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_list_all_filters_by_country_priority(monkeypatch):
    fake_cursor = _FakeCursor(rows=[{"id": 1, "name": "EUR-Lex", "country_priority": "P1"}])
    monkeypatch.setattr(repository_module, "get_cursor", lambda *args, **kwargs: _CursorContext(fake_cursor))

    rows = OfficialSourceRepository().list_all(country_priorities=["P1"], enabled_only=True)

    sql, params = fake_cursor.executed[0]
    assert "JOIN countries c ON os.country_code = c.code" in sql
    assert "c.priority::text = ANY(%s)" in sql
    assert "os.enabled = TRUE" in sql
    assert params == [["P1"]]
    assert rows[0]["name"] == "EUR-Lex"


def test_list_history_orders_desc(monkeypatch):
    fake_cursor = _FakeCursor(rows=[{"id": 10, "status": "success"}])
    monkeypatch.setattr(repository_module, "get_cursor", lambda *args, **kwargs: _CursorContext(fake_cursor))

    rows = OfficialSourceRepository().list_history("src-1", limit=5)

    sql, params = fake_cursor.executed[0]
    assert "FROM official_source_history" in sql
    assert "ORDER BY started_at DESC LIMIT %s" in sql
    assert params == ("src-1", 5)
    assert rows[0]["status"] == "success"
