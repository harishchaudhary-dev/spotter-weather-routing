import pytest
import requests

from routing.providers import http


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


@pytest.fixture
def respond(monkeypatch):
    def install(result):
        class FakeSession:
            def get(self, *a, **k):
                if isinstance(result, Exception):
                    raise result
                return result

        monkeypatch.setattr(http, "session", lambda: FakeSession())

    return install


@pytest.mark.parametrize(
    "reason, hint",
    [
        ("Minutely API request limit exceeded. Please try again in one minute.", "wait a minute"),
        ("Hourly API request limit exceeded. Please try again in the next hour.", "within the hour"),
        ("Daily API request limit exceeded. Please try again tomorrow.", "midnight UTC"),
        (None, "wait a minute"),
    ],
)
def test_rate_limit_message_names_the_quota(respond, reason, hint):
    respond(FakeResponse(429, {"error": True, "reason": reason} if reason else None))
    with pytest.raises(http.ProviderError, match=f"rate limit reached.*{hint}"):
        http.get_json("https://x", service="Weather service")


def test_network_failure_is_reported_as_unreachable(respond):
    respond(requests.ConnectionError("boom"))
    with pytest.raises(http.ProviderError, match="unreachable"):
        http.get_json("https://x", service="Routing service")


def test_non_json_body_is_rejected(respond):
    respond(FakeResponse(200))
    with pytest.raises(http.ProviderError, match="invalid response"):
        http.get_json("https://x", service="Geocoder")


def test_accepted_error_status_returns_body(respond):
    respond(FakeResponse(400, {"code": "NoRoute"}))
    assert http.get_json("https://x", service="Routing service", ok_statuses=(200, 400)) == {"code": "NoRoute"}
