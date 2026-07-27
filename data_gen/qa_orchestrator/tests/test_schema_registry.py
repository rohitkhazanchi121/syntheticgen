import json
from io import BytesIO

import pytest

from qa_orchestrator.services.syn_dataloader.syntheticgen import schema_registry


class _DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_apicurio_schema_requires_url(monkeypatch):
    monkeypatch.delenv("APICURIO_REGISTRY_URL", raising=False)

    with pytest.raises(ValueError, match="APICURIO_REGISTRY_URL"):
        schema_registry.fetch_apicurio_schema(subject="s", version="1")


def test_fetch_apicurio_schema_builds_request_and_parses_response(monkeypatch):
    monkeypatch.setenv("APICURIO_REGISTRY_URL", "https://registry.example")

    captured = {}

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["accept"] = request.get_header("Accept")
        captured["timeout"] = timeout
        return _DummyResponse(
            {
                "type": "record",
                "name": "telemetry",
                "fields": [{"name": "id", "type": "string"}],
            }
        )

    monkeypatch.setattr(schema_registry.urllib.request, "urlopen", _fake_urlopen)

    schema = schema_registry.fetch_apicurio_schema(
        subject="telemetry-value",
        version="7",
        group_id="default",
    )

    assert schema["name"] == "telemetry"
    assert "/groups/default/artifacts/telemetry-value/versions/7/content" in captured["url"]
    assert captured["accept"] == "application/json"
    assert captured["timeout"] == 30
