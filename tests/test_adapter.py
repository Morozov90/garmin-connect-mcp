import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from http_fixtures import ScriptedHTTP, token

from garmin_training_mcp.adapter import GarminAdapter, SafeSession
from garmin_training_mcp.config import Settings, save_key
from garmin_training_mcp.errors import GarminError


def adapter(tmp_path, http, monkeypatch, sleeps=None):
    monkeypatch.delenv("GARMIN_PERSONAL_API_KEY", raising=False)
    settings = Settings(tmp_path / "config")
    save_key(settings, "SYNTHETIC-SECRET-KEY")

    def session():
        s = SafeSession(sleep=(sleeps if sleeps is not None else []).append)
        s.mount("https://", http)
        return s

    return GarminAdapter(settings, session_factory=session), settings


def test_official_sdk_exchange_cache_and_queries(tmp_path, monkeypatch):
    http = ScriptedHTTP((200, token()), (200, []), (200, []))
    api, settings = adapter(tmp_path, http, monkeypatch)
    assert api.call("search_activities", start=0, limit=3, activity_type="running") == []
    assert api.call("get_daily_sleep", "2026-10-01") == []
    assert [r.method for r in http.requests] == ["POST", "GET", "GET"]
    assert "activityType=running" in http.requests[1].url
    assert http.requests[0].headers["Authorization"] == "ApiKey SYNTHETIC-SECRET-KEY"
    assert settings.cache_file.stat().st_mode & 0o777 == 0o600
    assert json.loads(settings.cache_file.read_text())["access_token"].startswith("synthetic.")
    assert not list(settings.directory.glob(".token-*"))


def test_stale_401_refreshes_only_once(tmp_path, monkeypatch):
    http = ScriptedHTTP(
        (200, token()), (401, "SYNTHETIC-SECRET-KEY"), (200, token()), (401, "SYNTHETIC-SECRET-KEY")
    )
    api, _ = adapter(tmp_path, http, monkeypatch)
    with pytest.raises(GarminError) as exc:
        api.call("get_activity", "42")
    assert exc.value.code == "authentication"
    assert "SYNTHETIC" not in str(exc.value)
    assert len(http.requests) == 4


def test_expiring_cache_renews(tmp_path, monkeypatch):
    http = ScriptedHTTP((200, token()), (200, {}), (200, token()), (200, {}))
    api, settings = adapter(tmp_path, http, monkeypatch)
    api.call("get_activity", "42")
    cache = json.loads(settings.cache_file.read_text())
    cache["expires_at"] = 1
    settings.cache_file.write_text(json.dumps(cache))
    api.call("get_activity", "42")
    assert [r.method for r in http.requests] == ["POST", "GET", "POST", "GET"]


@pytest.mark.parametrize(
    "status,code",
    [
        (403, "authentication"),
        (404, "not_found"),
        (400, "upstream_rejected"),
        (429, "rate_limited"),
        (500, "upstream"),
    ],
)
def test_bounded_http_failures(tmp_path, monkeypatch, status, code):
    http = ScriptedHTTP((200, token()), *((status, "private upstream body") for _ in range(3)))
    api, _ = adapter(tmp_path, http, monkeypatch)
    with pytest.raises(GarminError) as exc:
        api.call("get_activity", "42")
    assert exc.value.code == code
    assert "private upstream" not in str(exc.value)
    assert len(http.requests) <= 4


def test_retry_after_respected_and_long_wait_returned(tmp_path, monkeypatch):
    sleeps = []
    http = ScriptedHTTP(
        (200, token()),
        (429, "", {"Retry-After": "2"}),
        (200, {}),
        (429, "", {"Retry-After": "120"}),
    )
    api, _ = adapter(tmp_path, http, monkeypatch, sleeps)
    assert api.call("get_activity", "42") == {}
    assert sleeps == [2.0]
    with pytest.raises(GarminError) as exc:
        api.call("get_activity", "42")
    assert exc.value.retry_after_seconds == 120
    assert sleeps == [2.0]


def test_timeout_and_bad_json_are_safe(tmp_path, monkeypatch):
    http = ScriptedHTTP((200, token()), *(requests.Timeout("SYNTHETIC-SECRET") for _ in range(3)))
    api, _ = adapter(tmp_path, http, monkeypatch)
    with pytest.raises(GarminError, match="timed out"):
        api.call("get_activity", "42")
    http.responses.append((200, "not-json SYNTHETIC-SECRET"))
    with pytest.raises(GarminError) as exc:
        api.call("get_activity", "42")
    assert exc.value.code == "upstream_schema"
    assert "SYNTHETIC" not in str(exc.value)


def test_origin_override_and_redirects_blocked(tmp_path, monkeypatch):
    http = ScriptedHTTP((302, "", {"Location": "https://elsewhere.example"}))
    api, _ = adapter(tmp_path, http, monkeypatch)
    monkeypatch.setenv("GARMIN_PERSONAL_API_BASE_URL", "https://elsewhere.example")
    with pytest.raises(GarminError, match="override"):
        api.call("get_activity", "42")
    assert not http.requests
    monkeypatch.delenv("GARMIN_PERSONAL_API_BASE_URL")
    with pytest.raises(GarminError):
        api.call("get_activity", "42")
    assert len(http.requests) == 1


def test_concurrent_calls_share_one_atomic_cache(tmp_path, monkeypatch):
    http = ScriptedHTTP((200, token()), *((200, {}) for _ in range(8)))
    api, settings = adapter(tmp_path, http, monkeypatch)
    with ThreadPoolExecutor(4) as pool:
        assert list(pool.map(lambda _: api.call("get_activity", "42"), range(8))) == [{}] * 8
    assert sum(r.method == "POST" for r in http.requests) == 1
    assert json.loads(settings.cache_file.read_text())["expires_at"] > 0


def test_response_size_limit(tmp_path, monkeypatch):
    http = ScriptedHTTP((200, token()), (200, "x" * (4 * 1024 * 1024 + 1)))
    api, _ = adapter(tmp_path, http, monkeypatch)
    with pytest.raises(GarminError) as exc:
        api.call("get_activity", "42")
    assert exc.value.code == "response_too_large"


def test_body_deadline_interrupts_a_slow_chunk(tmp_path, monkeypatch):
    import threading

    from garmin_training_mcp import adapter as module

    class DripStream:
        def __init__(self):
            self.stopped = threading.Event()

        def read(self, amount):
            # A filled-chunk read can hide continual small network progress.
            self.stopped.wait(0.3)
            return b""

        def shutdown(self):
            self.stopped.set()

        def close(self):
            pass

    stream = DripStream()

    class DripHTTP(ScriptedHTTP):
        def send(self, request, **kwargs):
            response = super().send(request, **kwargs)
            response.raw = stream
            return response

    monkeypatch.setattr(module, "BODY_TIMEOUT_SECONDS", 0.02, raising=False)
    session = SafeSession(sleep=lambda _: None)
    session.mount("https://", DripHTTP((200, "")))
    with pytest.raises(GarminError) as exc:
        session.get("https://personal.connectapi.garmin.com/activity-service/activity/42")
    assert exc.value.code == "timeout"
    assert stream.stopped.is_set()
