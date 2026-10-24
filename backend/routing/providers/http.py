import logging
import time
from functools import lru_cache

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)


class ProviderError(Exception):
    """An upstream service failed or returned something unusable (maps to HTTP 502)."""


class RateLimitError(ProviderError):
    """The provider refused us for quota reasons. `scope` is "minute", "hour" or "day"."""

    def __init__(self, message: str, scope: str):
        super().__init__(message)
        self.scope = scope


class NotFoundError(Exception):
    """The request was valid but has no answer, e.g. unknown place or no road route (HTTP 422)."""


@lru_cache(maxsize=1)
def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.6,
        # 429 is deliberately absent: hammering a rate-limited API only burns more quota.
        # Callers decide whether a quota error is worth waiting out (see weather._fetch).
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,  # hand back the final response so we can report *why* it failed
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=16)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers["User-Agent"] = settings.HTTP_USER_AGENT
    return s


def get_json(url: str, params: dict | None = None, *, service: str, ok_statuses: tuple[int, ...] = (200,)):
    started = time.perf_counter()
    try:
        response = session().get(url, params=params, timeout=settings.HTTP_TIMEOUT_S)
    except requests.RequestException as exc:
        raise ProviderError(f"{service} is unreachable right now. Please try again.") from exc
    elapsed_ms = (time.perf_counter() - started) * 1000
    log.info("%s %s %.0fms", service, response.status_code, elapsed_ms)
    if response.status_code == 429:
        scope = _rate_limit_scope(response)
        raise RateLimitError(f"{service} rate limit reached. {_HINTS[scope]}", scope)
    if response.status_code not in ok_statuses:
        raise ProviderError(f"{service} returned HTTP {response.status_code}.")
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError(f"{service} returned an invalid response.") from exc


_HINTS = {
    "minute": "Please wait a minute and try again.",
    "hour": "The free hourly quota is used up; please try again within the hour.",
    "day": "The free daily quota is used up; it resets at midnight UTC.",
}


def _rate_limit_scope(response) -> str:
    """Free tiers enforce minutely, hourly and daily quotas; work out which one we hit."""
    try:
        reason = str(response.json().get("reason", "")).lower()
    except (ValueError, AttributeError):
        reason = ""
    if "daily" in reason:
        return "day"
    if "hourly" in reason:
        return "hour"
    return "minute"
