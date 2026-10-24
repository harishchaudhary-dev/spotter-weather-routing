import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient


@pytest.fixture
def client():
    cache.clear()
    return APIClient()


def test_vercel_host_is_allowed(client):
    assert client.get("/api/health", HTTP_HOST="my-app-lac.vercel.app").status_code == 200


def test_vercel_frontend_origin_gets_cors_header(client):
    res = client.get("/api/health", HTTP_ORIGIN="https://stormline-web.vercel.app")
    assert res["Access-Control-Allow-Origin"] == "https://stormline-web.vercel.app"


def test_unknown_origin_gets_no_cors_header(client):
    res = client.get("/api/health", HTTP_ORIGIN="https://evil.example.com")
    assert "Access-Control-Allow-Origin" not in res


@override_settings(FRONTEND_DIST=__import__("pathlib").Path("/nonexistent"))
def test_api_only_deploy_root_describes_the_api(client):
    res = client.get("/")
    assert res.status_code == 200 and res.json()["service"] == "Stormline API"
