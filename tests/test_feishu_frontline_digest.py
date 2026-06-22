import notifier.feishu as feishu_module
from notifier.feishu import AlertMessage, FeishuNotifier
from datetime import date


def test_feishu_frontline_digest_card_formats_sources_verified_and_windows(monkeypatch):
    captured = {}
    today = date.today().isoformat()
    monkeypatch.setattr(
        feishu_module.requests,
        "Session",
        lambda: type("S", (), {"headers": {}, "post": lambda self, *args, **kwargs: None})(),
        raising=False,
    )
    notifier = FeishuNotifier(webhook_url="https://example.test/webhook")

    def fake_send(payload):
        captured["payload"] = payload
        return True

    monkeypatch.setattr(notifier, "_send", fake_send)

    ok = notifier.send_frontline_digest_card(
        new_sources=[
            {
                "title": "Example Cybersecurity Regulation",
                "country_name": "欧盟",
                "country_code": "EU",
                "entry_type": "regulation",
                "source_name": "EU Official Journal",
                "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R2847",
                "published_date": today,
            }
        ],
        new_verified=[
            {
                "name": "Verified Cybersecurity Act",
                "country_name": "英国",
                "country_code": "GB",
                "mandatory": "mandatory",
                "official_url": "https://www.legislation.gov.uk/ukpga/2022/46/contents",
            }
        ],
        upcoming_by_window={
            30: [
                {
                    "name": "CRA",
                    "country_name": "欧盟",
                    "days_until_effective": 20,
                    "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
                }
            ],
            90: [
                {
                    "name": "PSTI",
                    "country_name": "英国",
                    "days_until_effective": 70,
                    "official_url": "https://www.legislation.gov.uk/uksi/2023/1007/contents",
                }
            ],
        },
        ai_discovery_stats={
            "candidate_count": 5,
            "accepted_count": 3,
            "rejected_count": 2,
            "artifact_pending_count": 3,
            "artifact_downloaded_count": 1,
        },
        ai_discovery_candidates=[
            {
                "title": "Recent official AI-discovered candidate",
                "country_name": "新加坡",
                "country_code": "SG",
                "entry_type": "certification",
                "source_url": "https://www.csa.gov.sg/our-programmes/cybersecurity-labelling-scheme",
                "published_date": today,
                "source_payload": {
                    "raw_candidate": {
                        "title_zh": "近期官方候选",
                        "summary_zh": "新加坡官方发布的产品网络安全认证线索。",
                    }
                },
            },
            {
                "title": "Historical official AI-discovered candidate",
                "country_name": "越南",
                "country_code": "VN",
                "entry_type": "certification",
                "source_url": "https://english.mst.gov.vn/6000-systems-for-e-transactions-receive-a-trust-mark-label-197241205094451834.htm",
                "published_date": "2024-12-05",
                "source_payload": {
                    "raw_candidate": {
                        "title_zh": "历史官方补库线索",
                    }
                },
            },
            {
                "title": "Unknown-date official AI-discovered candidate",
                "country_name": "印度",
                "country_code": "IN",
                "entry_type": "standard",
                "source_url": "https://www.stqc.gov.in/",
                "source_payload": {
                    "raw_candidate": {
                        "title_zh": "发布日期待核验的官方标准线索",
                    }
                },
            }
        ],
        official_dynamics=[
            {
                "title": "6,000 systems for e-transactions receive a 'trust mark' label",
                "country_name": "越南",
                "country_code": "VN",
                "entry_type": "certification",
                "source_url": "https://english.mic.gov.vn/6000-systems-for-e-transactions-receive-a-trust-mark-label-197241205080947425.htm",
                "published_date": today,
                "source_payload": {
                    "raw_candidate": {
                        "title_zh": "6000个电子交易系统获得信任标识",
                        "summary_zh": "越南官方新闻，可作为日常动态参考。",
                    }
                },
            }
        ],
        lookback_hours=24,
    )

    assert ok is True
    payload = captured["payload"]
    assert payload["msg_type"] == "interactive"
    text = str(payload)
    assert "今日网安合规早报" in text
    assert "今日看点" in text
    assert "待核验官方线索" in text
    assert "官方源监测" in text
    assert "合规日程" in text
    assert "今日监测重点集中在1条待核验官方线索、1条网安合规动态和1条官方源监测。" in text
    assert "正式知识库新增1条已验证入库记录。" in text
    assert "近期日程中有1个30天内适用节点需要关注。" in text
    assert "以下内容均保留官方原文链接，便于追溯。" in text
    assert "AI待核验线索" not in text
    assert "30天内节点" not in text
    assert "90天内节点" not in text
    assert "180天内节点" not in text
    assert "360天内节点" not in text
    assert "今日AI发现" not in text
    assert "统计范围" not in text
    assert "AI 已联网搜索" not in text
    assert "通过官方域名/主题硬校验" not in text
    assert "未审核前不作为正式结论" not in text
    assert "原始线索" not in text
    assert "通过硬校验" not in text
    assert "拒绝" not in text
    assert "待下载工件" not in text
    assert "新发现官方候选" not in text
    assert "系统抓取，待核验" not in text
    assert "Example Cybersecurity Regulation" in text
    assert "今日已验证入库（1条）" in text
    assert "官方源监测（1条）" in text
    assert "待核验官方线索（1条）" in text
    assert "网安合规动态（1条）" in text
    assert "AI近期新动态" not in text
    assert "AI历史补库线索" not in text
    assert "AI日期待核验线索" not in text
    assert "处理状态" not in text
    assert "AI 联网发现官方候选" not in text
    assert "内置 AI 通道开启联网搜索" not in text
    assert "近期官方候选（原文：Recent official AI-discovered candidate）" in text
    assert "新加坡官方发布的产品网络安全认证线索。" in text
    assert "新加坡(SG) · 认证" in text
    assert "历史官方补库线索" not in text
    assert "发布日期待核验的官方标准线索" not in text
    assert "印度(IN) · 标准" not in text
    assert "网安合规动态" in text
    assert "只用于情报参考" not in text
    assert "不进入法规/认证候选" not in text
    assert "RAG 或规格库" not in text
    assert "6000个电子交易系统获得信任标识（原文：6,000 systems for e-transactions receive a 'trust mark' label）" in text
    assert "6,000 systems for e-transactions receive a 'trust mark' label" in text
    assert "摘要：越南官方新闻，可作为日常动态参考。" in text
    assert "https://english.mic.gov.vn/6000-systems-for-e-transactions-receive-a-trust-mark-label-197241205080947425.htm" in text
    assert f"发布日期：{today}" in text
    assert "发布日期待核验" not in text
    assert "官方原文" in text
    assert "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R2847" in text
    assert "https://www.csa.gov.sg/our-programmes/cybersecurity-labelling-scheme" in text
    assert "https://english.mst.gov.vn/6000-systems-for-e-transactions-receive-a-trust-mark-label-197241205094451834.htm" not in text
    assert "30天内" in text
    assert "90天内" in text
    assert "窗口概览：30天内 1；90天内 1" in text
    assert "最近节点：" in text


def test_feishu_frontline_digest_normalizes_taiwan_display_name(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        feishu_module.requests,
        "Session",
        lambda: type("S", (), {"headers": {}, "post": lambda self, *args, **kwargs: None})(),
        raising=False,
    )
    notifier = FeishuNotifier(webhook_url="https://example.test/webhook")
    monkeypatch.setattr(notifier, "_send", lambda payload: captured.setdefault("payload", payload) or True)

    assert notifier.send_frontline_digest_card(
        new_sources=[
            {
                "title": "TW Cybersecurity Certification",
                "country_name": "台湾",
                "country_code": "TW",
                "entry_type": "regulation",
                "source_url": "https://example.tw/security",
            }
        ],
        new_verified=[],
        upcoming_by_window={},
        ai_discovery_stats={},
        ai_discovery_candidates=[],
        official_dynamics=[],
    )

    text = str(captured["payload"])
    assert "中国台湾(TW) · 法律法规" in text
    assert "· 台湾(TW)" not in text
    assert "**台湾(TW)" not in text


def test_feishu_alert_and_weekly_report_include_official_source_links(monkeypatch):
    captured = []
    monkeypatch.setattr(
        feishu_module.requests,
        "Session",
        lambda: type("S", (), {"headers": {}, "post": lambda self, *args, **kwargs: None})(),
        raising=False,
    )
    notifier = FeishuNotifier(webhook_url="https://example.test/webhook")
    monkeypatch.setattr(notifier, "_send", lambda payload: captured.append(payload) or True)

    notifier.send_alert(
        AlertMessage(
            title="CRA 报告义务提醒",
            content="请依据官方原文确认。",
            effective_date="2026-09-11",
            source_url="https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
        )
    )
    notifier.send_weekly_report_card(
        total_records=1,
        country_count=1,
        candidate_this_week=0,
        verified_this_week=0,
        source_artifacts_this_week=0,
        quarantined_this_week=0,
        upcoming_alerts=[
            {
                "name": "CRA",
                "country_name": "欧盟",
                "days_until_effective": 20,
                "milestone_label_zh": "报告义务开始适用",
                "official_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj",
            }
        ],
    )

    text = str(captured)
    assert "官方原文" in text
    assert "https://eur-lex.europa.eu/eli/reg/2024/2847/oj" in text


def test_feishu_send_retries_rate_limit_code(monkeypatch):
    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Session:
        def __init__(self):
            self.headers = {}
            self.calls = 0

        def post(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return _Resp({"code": 11232, "msg": "frequency limited"})
            return _Resp({"code": 0, "msg": "ok"})

    session = _Session()
    monkeypatch.setattr(feishu_module.requests, "Session", lambda: session, raising=False)
    sleeps = []
    monkeypatch.setattr(feishu_module.time, "sleep", lambda delay: sleeps.append(delay))

    notifier = FeishuNotifier(webhook_url="https://example.test/webhook")

    assert notifier.send_text("早报测试") is True
    assert session.calls == 2
    assert sleeps == [5]


def test_frontline_digest_card_shows_ai_collection_failure(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        feishu_module.requests,
        "Session",
        lambda: type("S", (), {"headers": {}, "post": lambda self, *args, **kwargs: None})(),
        raising=False,
    )
    notifier = FeishuNotifier(webhook_url="https://example.test/webhook")
    monkeypatch.setattr(notifier, "_send", lambda payload: captured.setdefault("payload", payload) or True)

    assert notifier.send_frontline_digest_card(
        new_sources=[],
        new_verified=[],
        upcoming_by_window={},
        ai_discovery_stats={
            "candidate_count": 0,
            "failed_run_count": 1,
            "latest_status": "failed",
            "latest_error": "Error code: 403 - insufficient_user_quota 用户额度不足",
        },
        ai_discovery_candidates=[],
        official_dynamics=[],
    )

    text = str(captured["payload"])
    assert "采集状态" in text
    assert "今日早报可能不完整" in text
    assert "内置 AI 通道额度不足" in text
    assert "确认无新增" in text
