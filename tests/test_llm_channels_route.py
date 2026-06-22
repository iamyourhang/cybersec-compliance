from fastapi import FastAPI
from fastapi.testclient import TestClient

from collector.providers.base import LLMResponse
from collector.providers.router_models import ChannelConfig
from admin.api.auth import get_current_user
from admin.api.routes.llm_channels import get_channel_repository, router


class _FakeRepo:
    def __init__(self):
        self.marked = []

    def list_all(self):
        return [
            {
                "id": "ch-1",
                "name": "primary",
                "provider_type": "openai_compatible",
                "base_url": "https://example.com/v1",
                "model": "gpt-4.1",
                "priority": 1,
                "enabled": True,
                "supports_web_search": False,
                "quota_exhausted": False,
                "manual_pause": False,
            }
        ]

    def mark_quota_exhausted(self, channel_id, error):
        self.marked.append(channel_id)

    def add_event(self, channel_id, event_type, message, raw_error):
        pass

    def get_channel(self, channel_id):
        if channel_id != "ch-1":
            return None
        return ChannelConfig(
            id="ch-1",
            name="primary",
            provider_type="openai_compatible",
            base_url="https://example.com/v1",
            api_key="secret",
            model="gpt-4.1",
            priority=1,
            enabled=True,
            supports_web_search=False,
            quota_exhausted=False,
            manual_pause=False,
        )


def _build_client(repo):
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.dependency_overrides[get_channel_repository] = lambda: repo
    app.include_router(router, prefix="/api/llm-channels")
    return TestClient(app)


def test_list_llm_channels_returns_items():
    repo = _FakeRepo()
    client = _build_client(repo)

    response = client.get("/api/llm-channels/")

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "primary"


def test_mark_quota_exhausted_updates_status():
    repo = _FakeRepo()
    client = _build_client(repo)

    response = client.post("/api/llm-channels/ch-1/mark-quota-exhausted")

    assert response.status_code == 200
    assert repo.marked == ["ch-1"]


def test_test_existing_channel_returns_probe_result(monkeypatch):
    repo = _FakeRepo()
    client = _build_client(repo)

    def _fake_build_provider(channel):
        assert channel.id == "ch-1"

        class _Adapter:
            def chat(self, messages, **kwargs):
                return LLMResponse(
                    content="OK",
                    provider_name=channel.name,
                    model=channel.model,
                    latency_ms=123.4,
                )

        return _Adapter()

    monkeypatch.setattr("admin.api.routes.llm_channels.build_provider_from_channel", _fake_build_provider)

    response = client.post("/api/llm-channels/ch-1/test")

    assert response.status_code == 200
    assert response.json()["model"] == "gpt-4.1"
    assert response.json()["content"] == "OK"
