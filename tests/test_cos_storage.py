import sys
from types import SimpleNamespace

from collector.document.cos_storage import CosStorage


def test_cos_storage_uses_extended_timeout(monkeypatch):
    captured = {}

    class _FakeConfig:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class _FakeClient:
        def __init__(self, config):
            self.config = config

    monkeypatch.setitem(
        sys.modules,
        "qcloud_cos",
        SimpleNamespace(CosConfig=_FakeConfig, CosS3Client=_FakeClient),
    )
    monkeypatch.setenv("COS_CLIENT_TIMEOUT_SECONDS", "300")

    storage = CosStorage.__new__(CosStorage)
    storage._build_client(
        SimpleNamespace(
            cos=SimpleNamespace(
                region="ap-guangzhou",
                secret_id="sid",
                secret_key="skey",
            )
        )
    )

    assert captured["Timeout"] == 300
