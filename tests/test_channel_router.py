from config.settings import Settings

from collector.providers.base import LLMResponse
from collector.providers.dashscope import _build_qwen_extra_body


def test_qwen3_extra_body_disables_thinking_for_extraction_latency():
    assert _build_qwen_extra_body("qwen3.6-plus", enable_web_search=False) == {
        "enable_thinking": False
    }
    assert _build_qwen_extra_body("qwen3.6-plus", enable_web_search=True) == {
        "enable_search": True,
        "enable_thinking": False,
        "search_options": {
            "forced_search": True,
            "search_strategy": "max",
            "enable_source": True,
        },
    }


def test_uniapi_search_extra_body_supports_verified_models_only():
    assert _build_qwen_extra_body("deepseek-v4-flash", enable_web_search=True) == {
        "enable_search": True,
        "search_options": {
            "forced_search": True,
            "search_strategy": "max",
            "enable_source": True,
        },
    }
    assert _build_qwen_extra_body("deepseek-v4-pro", enable_web_search=True) is None


def test_settings_loads_llm_router_fallback_json():
    settings = Settings(
        _env_file=None,
        LLM_ROUTER_FALLBACK_JSON=(
            '[{"name":"fallback","provider_type":"openai_compatible",'
            '"base_url":"https://example.com/v1","api_key":"k",'
            '"model":"gpt-4.1","priority":1,"enabled":true}]'
        ),
    )

    channels = settings.llm_router_fallback
    assert len(channels) == 1
    assert channels[0]["name"] == "fallback"


def test_channel_repository_falls_back_to_legacy_env_channels():
    from types import SimpleNamespace

    from collector.providers.channel_repository import ChannelRepository

    repo = ChannelRepository()
    repo._settings = SimpleNamespace(
        llm_router_fallback=[],
        uniapi=SimpleNamespace(
            api_key="uni-key",
            base_url="https://uni.example.com/",
            model="",
        ),
        volcengine=SimpleNamespace(
            api_key="volc-key",
            base_url="https://volc.example/v1",
            model_primary="volc-primary",
            model_fallback="volc-fallback",
        ),
        dashscope=SimpleNamespace(
            api_key="dash-key",
            base_url="https://dash.example/compatible-mode/v1",
            model="qwen-max",
        ),
        deepseek=SimpleNamespace(
            api_key="deep-key",
            base_url="https://deep.example/v1",
            model="deepseek-chat",
        ),
    )

    channels = repo._load_env_fallback_channels()

    assert [channel.name for channel in channels] == [
        "uniapi-primary",
        "volcengine-primary",
        "volcengine-fallback",
        "dashscope-default",
        "deepseek-default",
    ]
    assert channels[0].base_url == "https://uni.example.com/v1"
    assert channels[0].model == "volc-primary"
    assert channels[0].supports_web_search is False


def test_channel_repository_prefers_uniapi_override_even_when_db_channels_exist(monkeypatch):
    from types import SimpleNamespace

    from collector.providers.channel_repository import ChannelRepository

    repo = ChannelRepository()
    repo._settings = SimpleNamespace(
        llm_router_fallback=[],
        uniapi=SimpleNamespace(
            api_key="uni-key",
            base_url="https://uni.example.com/",
            model="chosen-model",
        ),
        volcengine=SimpleNamespace(api_key="", base_url="", model_primary="", model_fallback=""),
        dashscope=SimpleNamespace(api_key="", base_url="", model=""),
        deepseek=SimpleNamespace(api_key="", base_url="", model=""),
    )
    monkeypatch.setattr(
        repo,
        "_list_enabled_db_channels",
        lambda: [
            type(
                "C",
                (),
                {
                    "id": "db-1",
                    "name": "db-primary",
                    "provider_type": "openai_compatible",
                    "base_url": "https://db.example/v1",
                    "api_key": "db-key",
                    "model": "db-model",
                    "priority": 5,
                    "enabled": True,
                    "supports_web_search": False,
                    "quota_exhausted": False,
                    "manual_pause": False,
                },
            )()
        ],
    )

    channels = repo.list_routable_channels()

    assert [channel.name for channel in channels[:2]] == ["uniapi-primary", "db-primary"]


def test_channel_repository_marks_uniapi_qwen_search_capable(monkeypatch):
    from types import SimpleNamespace

    from collector.providers.channel_repository import ChannelRepository

    repo = ChannelRepository()
    repo._settings = SimpleNamespace(
        llm_router_fallback=[],
        uniapi=SimpleNamespace(
            api_key="uni-key",
            base_url="https://uni.example.com/",
            model="qwen3.6-plus",
        ),
        volcengine=SimpleNamespace(api_key="", base_url="", model_primary="", model_fallback=""),
        dashscope=SimpleNamespace(api_key="", base_url="", model=""),
        deepseek=SimpleNamespace(api_key="", base_url="", model=""),
    )
    monkeypatch.setattr(repo, "_list_enabled_db_channels", lambda: [])

    channels = repo.list_routable_channels()

    assert channels[0].name == "uniapi-primary"
    assert channels[0].supports_web_search is True


class FakeChannelRepository:
    def __init__(self, channels):
        self.channels = channels
        self.quota_marked = []
        self.events = []
        self.used_channel_ids = []

    def list_routable_channels(self):
        return self.channels

    def mark_quota_exhausted(self, channel_id, error):
        self.quota_marked.append(channel_id)

    def add_event(self, channel_id, event_type, message, raw_error):
        self.events.append((channel_id, event_type, message, raw_error))


def fake_factory(results_by_id):
    def _factory(channel):
        class _Adapter:
            def chat(self, messages, **kwargs):
                outcome = results_by_id[channel.id]
                if isinstance(outcome, Exception):
                    raise outcome
                return LLMResponse(
                    content=outcome,
                    provider_name=channel.name,
                    model=channel.model,
                )

        return _Adapter()

    return _factory


def test_channel_router_skips_quota_exhausted_channel():
    from collector.providers.channel_router import ChannelRouter
    from collector.providers.router_models import ChannelConfig

    repo = FakeChannelRepository(
        [
            ChannelConfig(
                id="1",
                name="a",
                provider_type="openai_compatible",
                base_url="https://a.example/v1",
                api_key="a",
                model="m1",
                priority=1,
                enabled=True,
                supports_web_search=False,
                quota_exhausted=True,
                manual_pause=False,
            ),
            ChannelConfig(
                id="2",
                name="b",
                provider_type="openai_compatible",
                base_url="https://b.example/v1",
                api_key="b",
                model="m2",
                priority=2,
                enabled=True,
                supports_web_search=False,
                quota_exhausted=False,
                manual_pause=False,
            ),
        ]
    )
    router = ChannelRouter(repository=repo, adapter_factory=fake_factory({"2": "ok"}))

    response = router.chat(messages=[{"role": "user", "content": "hi"}])

    assert response.content == "ok"
    assert repo.quota_marked == []


def test_channel_router_marks_quota_exhausted_and_falls_through():
    from collector.providers.channel_router import ChannelRouter
    from collector.providers.router_models import ChannelConfig, QuotaExhaustedError

    repo = FakeChannelRepository(
        [
            ChannelConfig(
                id="1",
                name="a",
                provider_type="openai_compatible",
                base_url="https://a.example/v1",
                api_key="a",
                model="m1",
                priority=1,
                enabled=True,
                supports_web_search=False,
                quota_exhausted=False,
                manual_pause=False,
            ),
            ChannelConfig(
                id="2",
                name="b",
                provider_type="openai_compatible",
                base_url="https://b.example/v1",
                api_key="b",
                model="m2",
                priority=2,
                enabled=True,
                supports_web_search=False,
                quota_exhausted=False,
                manual_pause=False,
            ),
        ]
    )
    router = ChannelRouter(
        repository=repo,
        adapter_factory=fake_factory({"1": QuotaExhaustedError("quota"), "2": "ok"}),
    )

    response = router.chat(messages=[{"role": "user", "content": "hi"}])

    assert response.content == "ok"
    assert repo.quota_marked == ["1"]
