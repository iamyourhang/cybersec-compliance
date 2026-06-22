import sys
import types


sys.modules.setdefault("requests", types.ModuleType("requests"))

from notifier.alert_scanner import AlertScanner


class _FakeNotifier:
    def __init__(self):
        self.digest_calls = []

    def send_alert(self, alert):
        return True

    def send_frontline_digest_card(self, **kwargs):
        self.digest_calls.append(kwargs)
        return True


class _FakeCursor:
    def __init__(self):
        self.sqls = []
        self._last_sql = ""

    def execute(self, sql, params=None):
        self.sqls.append(sql)
        self._last_sql = sql

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_effective_date_alerts_read_verified_index(monkeypatch):
    cursor = _FakeCursor()
    monkeypatch.setattr("notifier.alert_scanner.get_cursor", lambda: _CursorContext(cursor))
    captured = {}

    def _fake_milestones_for_date(target_date, mandatory_only=True):
        captured["target_date"] = target_date
        captured["mandatory_only"] = mandatory_only
        return []

    monkeypatch.setattr(
        "notifier.alert_scanner.ComplianceLifecycleRepository.get_milestones_for_date",
        _fake_milestones_for_date,
    )

    AlertScanner(notifier=_FakeNotifier())._process_effective_date_rule(rule_id=1, days_before=30)

    assert captured["mandatory_only"] is True
    assert cursor.sqls == []


def test_change_alerts_read_verified_index_and_review_events(monkeypatch):
    cursor = _FakeCursor()
    monkeypatch.setattr("notifier.alert_scanner.get_cursor", lambda: _CursorContext(cursor))

    AlertScanner(notifier=_FakeNotifier())._scan_change_alerts()

    sql = "\n".join(cursor.sqls)
    assert "FROM compliance_index ci" in sql
    assert "review_cases rc" in sql
    assert "ci.status='active'" in sql
    assert "ci.authenticity_status = 'verified'" in sql
    assert "country_name, official_url, source_rank" in sql
    assert "FROM compliance_knowledge ck" not in sql


def test_alert_scanner_run_does_not_send_morning_brief(monkeypatch):
    calls = {"effective": 0, "change": 0, "frontline": 0}
    scanner = AlertScanner(notifier=_FakeNotifier())

    monkeypatch.setattr(
        scanner,
        "_scan_effective_date_alerts",
        lambda: calls.__setitem__("effective", calls["effective"] + 1) or 0,
    )
    monkeypatch.setattr(
        scanner,
        "_scan_change_alerts",
        lambda: calls.__setitem__("change", calls["change"] + 1) or 0,
    )
    monkeypatch.setattr(
        scanner,
        "_scan_frontline_digest",
        lambda: calls.__setitem__("frontline", calls["frontline"] + 1) or 1,
    )

    stats = scanner.run()

    assert calls == {"effective": 1, "change": 1, "frontline": 0}
    assert stats["frontline_digest"] == 0


class _FrontlineCursor:
    def __init__(self):
        self.sqls = []
        self.params = []
        self._last_sql = ""

    def execute(self, sql, params=None):
        self.sqls.append(sql)
        self.params.append(params)
        self._last_sql = sql

    def fetchall(self):
        sql = self._last_sql
        if "sr.source_status = 'reference'" in sql:
            return [
                {
                    "id": "dyn-1",
                    "title": "Official trust mark news",
                    "country_code": "VN",
                    "country_name": "越南",
                    "entry_type": "certification",
                    "source_status": "reference",
                    "source_url": "https://english.mic.gov.vn/trust-mark-news.htm",
                    "published_date": "2026-05-15",
                    "created_at": "2026-05-15 08:45",
                }
            ]
        if "FROM source_records sr" in sql and "sr.discovery_method = 'ai_weekly_discovery'" in sql:
            return [
                {
                    "id": "ai-src-1",
                    "title": "AI-discovered official candidate",
                    "country_code": "SG",
                    "country_name": "新加坡",
                    "entry_type": "certification",
                    "source_status": "candidate",
                    "source_url": "https://www.csa.gov.sg/our-programmes/cybersecurity-labelling-scheme",
                    "published_date": "2026-05-10",
                    "created_at": "2026-05-15 08:30",
                }
            ]
        if "FROM source_records sr" in sql:
            return [
                {
                    "id": "src-1",
                    "title": "Example Cybersecurity Regulation",
                    "country_code": "EU",
                    "country_name": "欧盟",
                    "entry_type": "regulation",
                    "source_status": "candidate",
                    "source_url": "https://example.eu/law",
                    "source_name": "EU Official Journal",
                    "published_date": "2026-05-01",
                    "created_at": "2026-05-15 08:00",
                }
            ]
        if "JOIN review_cases rc" in sql:
            return [
                {
                    "id": "rec-1",
                    "name": "Verified Cybersecurity Act",
                    "country_code": "GB",
                    "country_name": "英国",
                    "entry_type": "regulation",
                    "mandatory": "mandatory",
                    "official_url": "https://legislation.gov.uk/",
                    "checked_at": "2026-05-15 09:00",
                }
            ]
        if "effective_date <= CURRENT_DATE + (%s * INTERVAL '1 day')" in sql:
            days = self.params[-1][0]
            return [
                {
                    "id": f"up-{days}",
                    "name": f"Upcoming {days}",
                    "country_code": "EU",
                    "country_name": "欧盟",
                    "entry_type": "regulation",
                    "mandatory": "mandatory",
                    "effective_date": "2026-06-01",
                    "days_until_effective": days,
                    "applicable_products": ["router"],
                    "official_url": "https://eur-lex.europa.eu/",
                }
            ]
        return []

    def fetchone(self):
        return None


def test_frontline_digest_reads_source_records_verified_records_and_upcoming_windows(monkeypatch):
    cursor = _FrontlineCursor()
    notifier = _FakeNotifier()
    captured_windows = []

    def _fake_upcoming(**kwargs):
        captured_windows.append(kwargs)
        days = kwargs["days"]
        return [
            {
                "id": f"up-{days}",
                "name": f"Upcoming {days}",
                "country_code": "EU",
                "country_name": "欧盟",
                "entry_type": "regulation",
                "mandatory": "mandatory",
                "effective_date": "2026-06-01",
                "milestone_date": "2026-06-01",
                "milestone_label_zh": "主要义务开始适用",
                "days_until_effective": days,
                "applicable_products": ["router"],
                "official_url": "https://eur-lex.europa.eu/",
            }
        ]

    monkeypatch.setattr("notifier.alert_scanner.get_cursor", lambda: _CursorContext(cursor))
    monkeypatch.setattr(
        "notifier.alert_scanner.ComplianceLifecycleRepository.get_upcoming_milestones",
        _fake_upcoming,
    )
    monkeypatch.setattr(
        "notifier.alert_scanner.AlertScanner._collect_ai_discovery_summary",
        lambda self, lookback_hours: {"candidate_count": 1, "accepted_count": 1, "rejected_count": 0},
    )
    monkeypatch.setattr("notifier.alert_scanner._probe_digest_link", lambda url: "reachable")
    monkeypatch.setattr(
        "notifier.alert_scanner.AlertScanner._attach_source_record_translations",
        lambda self, rows: rows,
    )

    sent = AlertScanner(notifier=notifier)._scan_frontline_digest(
        lookback_hours=24,
        upcoming_windows=(30, 90),
        limit=5,
    )

    assert sent == 1
    payload = notifier.digest_calls[0]
    assert payload["new_sources"][0]["source_url"] == "https://example.eu/law"
    assert payload["new_verified"][0]["name"] == "Verified Cybersecurity Act"
    assert payload["ai_discovery_stats"]["candidate_count"] == 1
    assert payload["ai_discovery_candidates"][0]["source_url"] == "https://www.csa.gov.sg/our-programmes/cybersecurity-labelling-scheme"
    assert payload["official_dynamics"][0]["source_status"] == "reference"
    assert payload["official_dynamics"][0]["source_url"] == "https://english.mic.gov.vn/trust-mark-news.htm"
    assert set(payload["upcoming_by_window"].keys()) == {30, 90}
    sql = "\n".join(cursor.sqls)
    assert "FROM source_records sr" in sql
    assert "NOT EXISTS" in sql
    assert "sr.compliance_id IS NULL" in sql
    assert "ci_existing.authenticity_status = 'verified'" in sql
    assert "FROM compliance_knowledge ck_existing" in sql
    assert sql.count("FROM compliance_knowledge ck_existing") >= 3
    assert "FROM source_records sr_seen" in sql
    assert sql.count("FROM source_records sr_seen") >= 3
    assert "ci_existing.official_url IN (sr.source_url, sr.artifact_url)" in sql
    assert sql.count("ci_existing.authenticity_status = 'verified'") >= 1
    assert "similarity(ci_existing.name, sr.title) >= 0.72" in sql
    assert "ci_existing.entry_type::text = sr.entry_type::text" in sql
    assert "ck_existing.entry_type::text = sr.entry_type::text" in sql
    assert "sr_seen.entry_type::text = sr.entry_type::text" in sql
    assert "sr.published_date IS NOT NULL" in sql
    assert "7 * INTERVAL '1 day'" in sql
    assert "sr.published_date" in sql
    assert "sr.source_status = 'reference'" in sql
    assert "COALESCE(sr.discovery_method, 'official_source') <> 'ai_weekly_discovery'" in sql
    assert "FROM compliance_index ci" in sql
    assert "ci.authenticity_status = 'verified'" in sql
    assert captured_windows == [{"days": 30, "limit": 5}, {"days": 90, "limit": 5}]


def test_frontline_digest_requires_recent_explicit_source_date_sql(monkeypatch):
    cursor = _FrontlineCursor()
    monkeypatch.setattr("notifier.alert_scanner.get_cursor", lambda: _CursorContext(cursor))
    monkeypatch.setattr(
        "notifier.alert_scanner.AlertScanner._attach_source_record_translations",
        lambda self, rows: rows,
    )

    scanner = AlertScanner(notifier=_FakeNotifier())
    scanner._collect_new_source_records(lookback_hours=9, limit=5)
    scanner._collect_ai_discovery_candidates(lookback_hours=9, limit=5)
    scanner._collect_official_dynamics(lookback_hours=9, limit=5)

    sql = "\n".join(cursor.sqls)
    assert "sr.published_date IS NOT NULL" in sql
    assert "sr.published_date >= CURRENT_DATE - (7 * INTERVAL '1 day')" in sql
    assert "sr.published_date IS NULL OR" not in sql


def test_frontline_digest_filters_permanent_not_found_source_links(monkeypatch):
    notifier = _FakeNotifier()
    scanner = AlertScanner(notifier=notifier)

    monkeypatch.setattr(
        scanner,
        "_collect_new_source_records",
        lambda lookback_hours, limit: [
            {
                "id": "good-src",
                "title": "Reachable official source",
                "country_code": "EU",
                "country_name": "欧盟",
                "entry_type": "regulation",
                "source_url": "https://official.example/reachable",
            },
            {
                "id": "bad-src",
                "title": "Broken official source",
                "country_code": "SE",
                "country_name": "瑞典",
                "entry_type": "certification",
                "source_url": "https://www.fmv.se/en/suppliers-and-partnerships/supplier-information/csec/certified-products/",
            },
        ],
    )
    monkeypatch.setattr(scanner, "_collect_new_verified_records", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_upcoming_windows", lambda upcoming_windows, limit: {})
    monkeypatch.setattr(scanner, "_collect_official_dynamics", lambda lookback_hours, limit: [])
    monkeypatch.setattr(
        scanner,
        "_collect_ai_discovery_candidates",
        lambda lookback_hours, limit: [
            {
                "id": "bad-ai",
                "title": "Broken AI source",
                "country_code": "SE",
                "country_name": "瑞典",
                "entry_type": "certification",
                "source_url": "https://www.fmv.se/en/suppliers-and-partnerships/supplier-information/csec/certified-products/",
            }
        ],
    )
    monkeypatch.setattr(
        scanner,
        "_collect_ai_discovery_summary",
        lambda lookback_hours: {"candidate_count": 1, "accepted_count": 1, "rejected_count": 0},
    )
    monkeypatch.setattr(
        "notifier.alert_scanner._probe_digest_link",
        lambda url: "permanent_unreachable" if "certified-products" in url else "reachable",
        raising=False,
    )

    sent = scanner._scan_frontline_digest(lookback_hours=24, upcoming_windows=(30,), limit=5)

    assert sent == 1
    payload = notifier.digest_calls[0]
    assert [item["id"] for item in payload["new_sources"]] == ["good-src"]
    assert payload["ai_discovery_candidates"] == []
    assert payload["ai_discovery_stats"]["raw_candidate_count"] == 1
    assert payload["ai_discovery_stats"]["candidate_count"] == 0


def test_frontline_digest_filters_cve_and_vulnerability_advisories(monkeypatch):
    notifier = _FakeNotifier()
    scanner = AlertScanner(notifier=notifier)

    monkeypatch.setattr(scanner, "_collect_new_source_records", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_new_verified_records", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_upcoming_windows", lambda upcoming_windows, limit: {})
    monkeypatch.setattr(scanner, "_collect_official_dynamics", lambda lookback_hours, limit: [])
    monkeypatch.setattr(
        scanner,
        "_collect_ai_discovery_candidates",
        lambda lookback_hours, limit: [
            {
                "id": "cve-ai",
                "title": "Vulnerabilidad crítica CVE-2026-24858 Bypass crítico de autenticación en productos Fortinet",
                "country_code": "BO",
                "country_name": "玻利维亚",
                "entry_type": "regulation",
                "source_url": "https://csirt.gob.bo/es/alertas-de-seguridad/vulnerabilidad-critica-cve-2026-24858-bypass-critico-de-autenticacion",
                "source_payload": {
                    "cyber_product_relevance_reason": "与网络安全产品本身的安全缺陷和补丁/缓解措施直接相关。",
                },
            }
        ],
    )
    monkeypatch.setattr(
        scanner,
        "_collect_ai_discovery_summary",
        lambda lookback_hours: {"candidate_count": 1, "accepted_count": 1, "rejected_count": 0},
    )
    monkeypatch.setattr("notifier.alert_scanner._probe_digest_link", lambda url: "reachable", raising=False)

    sent = scanner._scan_frontline_digest(lookback_hours=24, upcoming_windows=(30,), limit=5)

    assert sent == 0
    assert notifier.digest_calls == []


def test_frontline_digest_keeps_server_unverified_links(monkeypatch):
    notifier = _FakeNotifier()
    scanner = AlertScanner(notifier=notifier)

    monkeypatch.setattr(
        scanner,
        "_collect_new_source_records",
        lambda lookback_hours, limit: [
            {
                "id": "waf-src",
                "title": "Server blocked but not proven broken",
                "country_code": "SE",
                "country_name": "瑞典",
                "entry_type": "certification",
                "source_url": "https://official.example/cloudflare-blocked",
            }
        ],
    )
    monkeypatch.setattr(scanner, "_collect_new_verified_records", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_upcoming_windows", lambda upcoming_windows, limit: {})
    monkeypatch.setattr(scanner, "_collect_official_dynamics", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_ai_discovery_candidates", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_ai_discovery_summary", lambda lookback_hours: {})
    monkeypatch.setattr("notifier.alert_scanner._probe_digest_link", lambda url: "server_unverified", raising=False)

    sent = scanner._scan_frontline_digest(lookback_hours=24, upcoming_windows=(30,), limit=5)

    assert sent == 1
    payload = notifier.digest_calls[0]
    assert [item["id"] for item in payload["new_sources"]] == ["waf-src"]


def test_frontline_digest_honors_manual_digest_suppression(monkeypatch):
    notifier = _FakeNotifier()
    scanner = AlertScanner(notifier=notifier)

    monkeypatch.setattr(
        scanner,
        "_collect_new_source_records",
        lambda lookback_hours, limit: [
            {
                "id": "manual-bad-src",
                "title": "User reported 404 source",
                "country_code": "SE",
                "country_name": "瑞典",
                "entry_type": "certification",
                "source_url": "https://official.example/reported-404",
                "source_payload": {
                    "digest_suppression": {
                        "reason": "user_reported_404",
                    }
                },
            }
        ],
    )
    monkeypatch.setattr(scanner, "_collect_new_verified_records", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_upcoming_windows", lambda upcoming_windows, limit: {})
    monkeypatch.setattr(scanner, "_collect_official_dynamics", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_ai_discovery_candidates", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_ai_discovery_summary", lambda lookback_hours: {})
    monkeypatch.setattr("notifier.alert_scanner._probe_digest_link", lambda url: "reachable", raising=False)

    sent = scanner._scan_frontline_digest(lookback_hours=24, upcoming_windows=(30,), limit=5)

    assert sent == 0
    assert notifier.digest_calls == []


def test_frontline_digest_sends_when_ai_discovery_failed(monkeypatch):
    notifier = _FakeNotifier()
    scanner = AlertScanner(notifier=notifier)

    monkeypatch.setattr(scanner, "_collect_new_source_records", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_new_verified_records", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_upcoming_windows", lambda upcoming_windows, limit: {})
    monkeypatch.setattr(scanner, "_collect_official_dynamics", lambda lookback_hours, limit: [])
    monkeypatch.setattr(scanner, "_collect_ai_discovery_candidates", lambda lookback_hours, limit: [])
    monkeypatch.setattr(
        scanner,
        "_collect_ai_discovery_summary",
        lambda lookback_hours: {
            "candidate_count": 0,
            "failed_run_count": 1,
            "latest_status": "failed",
            "latest_error": "insufficient_user_quota",
        },
    )

    sent = scanner._scan_frontline_digest(lookback_hours=24, upcoming_windows=(30,), limit=5)

    assert sent == 1
    assert notifier.digest_calls[0]["ai_discovery_stats"]["latest_status"] == "failed"
