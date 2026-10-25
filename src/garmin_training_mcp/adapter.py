"""Official Garmin SDK with bounded transport and serialized, atomic token caching."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator
from garmin_personal_api.constants import BASE_URL_ENV_VAR, DEFAULT_BASE_URL, TOKEN_PATH
from garmin_personal_api.errors import GarminPersonalApiError

from .config import Settings, check_private, credential_lock, read_key
from .errors import GarminError

# Neither request bodies nor upstream exception strings belong in diagnostics.
for _logger in ("garmin_personal_api", "urllib3", "requests"):
    logging.getLogger(_logger).disabled = True


def retry_delay(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
        if not 0 <= seconds < float("inf"):
            return None
        return seconds
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


BODY_TIMEOUT_SECONDS = 20


def capture_body(response):
    """Interrupt the socket even if a streaming read never fills its chunk.

    Requests uses urllib3.HTTPResponse; its public shutdown method unblocks reads.
    Join the timer before closing/releasing the response to avoid a socket race.
    """
    expired = threading.Event()

    def expire():
        expired.set()
        # The stream may have finished and released its connection concurrently.
        with suppress(OSError, ValueError, RuntimeError):
            response.raw.shutdown()

    timer = threading.Timer(BODY_TIMEOUT_SECONDS, expire)
    timer.daemon = True
    timer.start()
    try:
        chunks, size = [], 0
        try:
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 4 * 1024 * 1024:
                    raise GarminError("response_too_large")
                if expired.is_set():
                    raise GarminError("timeout")
                chunks.append(chunk)
        except Exception:
            if expired.is_set():
                raise GarminError("timeout") from None
            raise
        if expired.is_set():
            raise GarminError("timeout")
        return b"".join(chunks)
    finally:
        timer.cancel()
        timer.join()


class SafeSession(requests.Session):
    """Fixed Garmin origin, no redirects/proxies, 4 MiB decoded body cap, <=3 GET attempts."""

    def __init__(self, *, sleep: Callable[[float], None] = time.sleep):
        super().__init__()
        self.trust_env = False
        self._sleep = sleep

    def request(self, method, url, **kwargs):
        if not url.startswith(DEFAULT_BASE_URL + "/"):
            raise GarminError("configuration")
        if method.upper() not in ("GET", "POST") or (
            method.upper() == "POST" and url != DEFAULT_BASE_URL + TOKEN_PATH
        ):
            raise GarminError("configuration")
        kwargs.update(timeout=(5, 15), allow_redirects=False, stream=True)
        attempts = 3 if method.upper() == "GET" else 1
        for attempt in range(attempts):
            try:
                response = super().request(method, url, **kwargs)
                try:
                    response._content = capture_body(response)
                    response._content_consumed = True
                finally:
                    response.close()
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt + 1 < attempts:
                    self._sleep(0.5 * (2**attempt))
                    continue
                code = "timeout" if isinstance(exc, requests.Timeout) else "network"
                raise GarminError(code) from None
            except requests.RequestException:
                raise GarminError("network") from None
            status = response.status_code
            if 200 <= status < 300:
                return response
            delay = retry_delay(response.headers.get("Retry-After"))
            if (
                status in (429, 500, 502, 503, 504)
                and attempt + 1 < attempts
                and (delay is None or delay <= 5)
            ):
                self._sleep(delay if delay is not None else 0.5 * (2**attempt))
                continue
            code = {
                401: "authentication",
                403: "authentication",
                404: "not_found",
                429: "rate_limited",
            }.get(status, "upstream" if status >= 500 else "upstream_rejected")
            raise GarminError(code, status=status, retry_after_seconds=delay)
        raise GarminError("upstream")  # All attempts either return or raise above.


class AtomicAuthenticator(PersonalApiAuthenticator):
    """Keep SDK serialization/expiry logic; replace its non-atomic cache writer.

    This private hook is covered by tests and intentionally tied to SDK 1.0.0.
    The caller holds credential_lock across reads, renewal and replacement.
    """

    def _write_cached_token(self, fingerprint, token):
        destination = self.bearer_token_cache_file
        fd, name = tempfile.mkstemp(prefix=".token-", dir=destination.parent)
        os.close(fd)
        try:
            self.bearer_token_cache_file = Path(name)
            super()._write_cached_token(fingerprint, token)
            os.replace(name, destination)
        finally:
            self.bearer_token_cache_file = destination
            Path(name).unlink(missing_ok=True)


class GarminAdapter:
    def __init__(self, settings: Settings, *, session_factory=SafeSession):
        self.settings = settings
        self.session_factory = session_factory

    def call(self, method: str, *args, **kwargs):
        # Only internal callers choose these method names; no generic endpoint MCP tool.
        if method not in {
            "search_activities",
            "get_activity",
            "get_daily_sleep",
            "get_daily_sleep_summaries",
            "get_daily_hrv_summaries",
            "get_daily_summaries",
            "get_user_profile_settings",
        }:
            raise GarminError("unsupported")
        if os.environ.get(BASE_URL_ENV_VAR) not in (None, DEFAULT_BASE_URL):
            raise GarminError("configuration")
        try:
            with credential_lock(self.settings):
                try:
                    key = read_key(self.settings)
                    check_private(self.settings.cache_file)
                except (OSError, ValueError):
                    raise GarminError("missing_credentials") from None
                with AtomicAuthenticator(
                    bearer_token_cache_file=self.settings.cache_file,
                    session=self.session_factory(),
                    timeout=15,
                ) as auth:
                    bearer = auth.obtain_token(key)
                    with GarminPersonalApiClient(
                        bearer.access_token,
                        session=self.session_factory(),
                        timeout=15,
                    ) as client:
                        try:
                            return getattr(client, method)(*args, **kwargs)
                        except GarminError as exc:
                            if exc.status != 401:
                                raise
                        # One refresh and replay, never an authentication loop.
                        bearer = auth.obtain_token(key, force_refresh=True)
                        client.update_bearer_token(bearer.access_token)
                        return getattr(client, method)(*args, **kwargs)
        except GarminError:
            raise
        except TimeoutError:
            raise GarminError("busy") from None
        except (requests.exceptions.JSONDecodeError, GarminPersonalApiError, TypeError, KeyError):
            raise GarminError("upstream_schema") from None
        except requests.RequestException:
            raise GarminError("network") from None
        except (OSError, ValueError):
            raise GarminError("configuration") from None
