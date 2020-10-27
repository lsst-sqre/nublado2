"""Tests for the Gafaelfawr authenticator.

Most of the authenticator machinery is deeply entangled with JupyterHub and
therefore can't be tested easily (and is also kept as simple as possible).
This tests the logic that's sufficiently separable to run in a test harness.
"""

from __future__ import annotations

import pytest
from tornado import web
from tornado.httputil import HTTPHeaders

from nublado2.auth import GafaelfawrAuthenticator, GafaelfawrLoginHandler


def test_authenticator() -> None:
    authenticator = GafaelfawrAuthenticator()
    assert authenticator.login_url("/hub") == "/hub/gafaelfawr/login"


def test_login_handler() -> None:
    headers = HTTPHeaders()
    with pytest.raises(web.HTTPError):
        GafaelfawrLoginHandler._build_auth_info(headers)

    headers.add("X-Auth-Request-User", "foo")
    assert GafaelfawrLoginHandler._build_auth_info(headers) == {
        "name": "foo",
        "auth_state": {
            "uid": None,
            "token": None,
            "groups": [],
        },
    }

    headers.add("X-Auth-Request-Groups", "group-one,group-two  ,  another")
    headers.add("X-Auth-Request-Token", "some-token")
    headers.add("X-Auth-Request-Uid", "4510")
    assert GafaelfawrLoginHandler._build_auth_info(headers) == {
        "name": "foo",
        "auth_state": {
            "uid": 4510,
            "token": "some-token",
            "groups": ["group-one", "group-two", "another"],
        },
    }
