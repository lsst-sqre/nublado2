"""Tests for the Gafaelfawr authenticator.

Most of the authenticator machinery is deeply entangled with JupyterHub and
therefore can't be tested easily (and is also kept as simple as possible).
This tests the logic that's sufficiently separable to run in a test harness.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from aioresponses import CallbackResult, aioresponses
from tornado import web
from tornado.httputil import HTTPHeaders

from nublado2.auth import GafaelfawrAuthenticator, GafaelfawrLoginHandler

if TYPE_CHECKING:
    from typing import Any, AsyncGenerator, Callable, Dict


@pytest.fixture(autouse=True)
async def config_mock() -> AsyncGenerator:
    """Use a mock NubladoConfig object."""
    with patch("nublado2.auth.NubladoConfig") as mock:
        mock.return_value = MagicMock()
        mock.return_value.base_url = "https://data.example.com/"
        mock.return_value.gafaelfawr_token = "admin-token"
        yield mock.return_value


def test_authenticator() -> None:
    authenticator = GafaelfawrAuthenticator()
    assert authenticator.get_handlers(MagicMock()) == [
        ("/gafaelfawr/login", GafaelfawrLoginHandler)
    ]
    assert authenticator.login_url("/hub") == "/hub/gafaelfawr/login"


def build_userinfo_handler(
    data: Dict[str, Any]
) -> Callable[..., CallbackResult]:
    def handler(url: str, **kwargs: Any) -> CallbackResult:
        assert kwargs["headers"] == {"Authorization": "bearer user-token"}
        return CallbackResult(payload=data, status=200)

    return handler


@pytest.mark.asyncio
async def test_login_handler(config_mock: MagicMock) -> None:
    headers = HTTPHeaders({"X-Auth-Request-Token": "user-token"})
    url = "https://data.example.com/auth/api/v1/user-info"

    # No headers.
    with aioresponses() as m:
        with pytest.raises(web.HTTPError):
            await GafaelfawrLoginHandler._build_auth_info(HTTPHeaders())

    # Invalid token.
    with aioresponses() as m:
        m.get(url, status=403)
        with pytest.raises(web.HTTPError):
            await GafaelfawrLoginHandler._build_auth_info(headers)

    # Bad API response payload.
    with aioresponses() as m:
        m.get(url, payload={}, status=200)
        with pytest.raises(web.HTTPError):
            await GafaelfawrLoginHandler._build_auth_info(headers)

    # Test minimum data.
    with aioresponses() as m:
        handler = build_userinfo_handler({"username": "foo", "uid": 1234})
        m.get(url, callback=handler)
        assert await GafaelfawrLoginHandler._build_auth_info(headers) == {
            "name": "foo",
            "auth_state": {
                "username": "foo",
                "uid": 1234,
                "token": "user-token",
                "groups": [],
            },
        }

    # Test full data.
    with aioresponses() as m:
        handler = build_userinfo_handler(
            {
                "username": "bar",
                "uid": 4510,
                "groups": [
                    {"name": "group-one", "id": 1726},
                    {"name": "another", "id": 6789},
                ],
            }
        )
        m.get(url, callback=handler)
        assert await GafaelfawrLoginHandler._build_auth_info(headers) == {
            "name": "bar",
            "auth_state": {
                "username": "bar",
                "uid": 4510,
                "token": "user-token",
                "groups": [
                    {"name": "group-one", "id": 1726},
                    {"name": "another", "id": 6789},
                ],
            },
        }
