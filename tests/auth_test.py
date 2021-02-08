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
from nublado2.nublado_config import NubladoConfig

if TYPE_CHECKING:
    from typing import Any, Callable, Dict


def test_authenticator() -> None:
    authenticator = GafaelfawrAuthenticator()
    assert authenticator.get_handlers(MagicMock()) == [
        ("/gafaelfawr/login", GafaelfawrLoginHandler)
    ]
    assert authenticator.login_url("/hub") == "/hub/gafaelfawr/login"


def build_handler(
    data: Dict[str, Any], valid: bool = True
) -> Callable[..., CallbackResult]:
    def handler(url: str, **kwargs: Any) -> CallbackResult:
        assert kwargs["data"] == {"token": "some-token"}
        response = {
            "token": {
                "data": data,
                "valid": valid,
            }
        }
        return CallbackResult(payload=response, status=200)

    return handler


@pytest.mark.asyncio
async def test_login_handler() -> None:
    # Using patch.object as a decorator doesn't work with Python 3.7.
    with patch.object(NubladoConfig, "get") as mock_config_get:
        mock_config_get.return_value = {}
        headers = HTTPHeaders({"X-Auth-Request-Token": "some-token"})
        with pytest.raises(web.HTTPError):
            await GafaelfawrLoginHandler._build_auth_info(headers)

        mock_config_get.return_value = {
            "base_url": "https://data.example.com/"
        }

        headers = HTTPHeaders()
        with pytest.raises(web.HTTPError):
            await GafaelfawrLoginHandler._build_auth_info(headers)

        headers.add("X-Auth-Request-Token", "some-token")

        # Invalid token.
        with aioresponses() as m:
            handler = build_handler({"uid": "foo"}, valid=False)
            m.post("https://data.example.com/auth/analyze", callback=handler)
            with pytest.raises(web.HTTPError):
                await GafaelfawrLoginHandler._build_auth_info(headers)

        # Bad API status.
        with aioresponses() as m:
            m.post(
                "https://data.example.com/auth/analyze", payload={}, status=500
            )
            with pytest.raises(web.HTTPError):
                await GafaelfawrLoginHandler._build_auth_info(headers)

        # Invalid response.
        with aioresponses() as m:
            m.post("https://data.example.com/auth/analyze", payload={})
            with pytest.raises(web.HTTPError):
                await GafaelfawrLoginHandler._build_auth_info(headers)

        # Test minimum data.
        with aioresponses() as m:
            handler = build_handler({"uid": "foo"})
            m.post("https://data.example.com/auth/analyze", callback=handler)
            assert await GafaelfawrLoginHandler._build_auth_info(headers) == {
                "name": "foo",
                "auth_state": {
                    "uid": None,
                    "token": "some-token",
                    "groups": [],
                },
            }

        # Test full data.
        with aioresponses() as m:
            handler = build_handler(
                {
                    "uid": "bar",
                    "uidNumber": "4510",
                    "isMemberOf": [
                        {"name": "group-one", "id": 1726},
                        {"name": "group-two", "id": "1618"},
                        {"name": "another", "id": 6789, "foo": "bar"},
                    ],
                }
            )
            m.post("https://data.example.com/auth/analyze", callback=handler)
            assert await GafaelfawrLoginHandler._build_auth_info(headers) == {
                "name": "bar",
                "auth_state": {
                    "uid": 4510,
                    "token": "some-token",
                    "groups": [
                        {"name": "group-one", "id": 1726},
                        {"name": "group-two", "id": 1618},
                        {"name": "another", "id": 6789},
                    ],
                },
            }

        # Check invalid format of isMemberOf.
        with aioresponses() as m:
            handler = build_handler(
                {"uid": "bar", "isMemberOf": [{"name": "foo", "id": ["foo"]}]}
            )
            m.post("https://data.example.com/auth/analyze", callback=handler)
            with pytest.raises(web.HTTPError):
                await GafaelfawrLoginHandler._build_auth_info(headers)

        # Test groups without GIDs.
        with aioresponses() as m:
            handler = build_handler(
                {
                    "uid": "bar",
                    "uidNumber": "4510",
                    "isMemberOf": [
                        {"name": "group-one", "id": 1726},
                        {"name": "group-two"},
                        {"name": "another", "id": 6789},
                    ],
                }
            )
            m.post("https://data.example.com/auth/analyze", callback=handler)
            assert await GafaelfawrLoginHandler._build_auth_info(headers) == {
                "name": "bar",
                "auth_state": {
                    "uid": 4510,
                    "token": "some-token",
                    "groups": [
                        {"name": "group-one", "id": 1726},
                        {"name": "another", "id": 6789},
                    ],
                },
            }
