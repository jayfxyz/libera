"""
Unit tests for auth routes. audible library calls are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.mark.asyncio
async def test_register_returns_auth_url():
    mock_cv = MagicMock()
    mock_cv.state = "test-state-123"

    with (
        patch("routes.auth.audible.auth.CodeVerifier", return_value=mock_cv),
        patch("routes.auth.audible.auth.build_login_url", return_value="https://amazon.com/login?foo=bar"),
        patch("routes.auth.audible.util.Locale", return_value=MagicMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/register", json={
                "locale": "us",
                "redirect_uri": "http://localhost:8080/api/auth/callback",
            })

    assert resp.status_code == 200
    data = resp.json()
    assert data["auth_url"] == "https://amazon.com/login?foo=bar"
    assert data["state"] == "test-state-123"


@pytest.mark.asyncio
async def test_register_invalid_locale():
    with patch("routes.auth.audible.util.Locale", side_effect=Exception("bad locale")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/register", json={
                "locale": "xx",
                "redirect_uri": "http://localhost:8080/api/auth/callback",
            })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_callback_unknown_state():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/auth/callback", json={
            "code": "abc123",
            "state": "nonexistent-state",
            "locale": "us",
        })
    assert resp.status_code == 400
    assert "Unknown" in resp.json()["detail"]
