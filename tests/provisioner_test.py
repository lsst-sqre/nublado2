"""Tests for the Provisioner class."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Callable, Dict, List, Union
from unittest.mock import MagicMock, Mock, patch

import pytest
import pytest_asyncio
from aioresponses import CallbackResult, aioresponses
from jupyterhub.spawner import Spawner
from jupyterhub.user import User

from nublado2.resourcemgr import ResourceManager


@pytest_asyncio.fixture(autouse=True)
async def config_mock() -> AsyncGenerator:
    """Use a mock NubladoConfig object."""
    with patch("nublado2.resourcemgr.NubladoConfig") as mock:
        mock.return_value = MagicMock()
        mock.return_value.base_url = "https://data.example.com/"
        mock.return_value.gafaelfawr_token = "admin-token"
        with patch("nublado2.provisioner.NubladoConfig") as mock:
            mock.return_value = MagicMock()
            mock.return_value.base_url = "https://data.example.com/"
            yield mock.return_value


def build_handler(
    username: str,
    uid: int,
    groups: List[Dict[str, Union[str, int]]],
) -> Callable[..., CallbackResult]:
    probe = 0

    def handler(url: str, **kwargs: Any) -> CallbackResult:
        nonlocal probe
        user_url = f"https://data.example.com/moneypenny/users/{username}"
        if str(url) == "https://data.example.com/moneypenny/users":
            assert kwargs["json"] == {
                "username": username,
                "uid": uid,
                "groups": groups,
            }
            return CallbackResult(status=303, headers={"Location": user_url})
        elif str(url) == user_url:
            result = {
                "username": username,
                "status": "commissioning" if probe == 0 else "active",
                "uid": uid,
                "groups": groups,
            }
            return CallbackResult(status=200, body=json.dumps(result))
        elif str(url) == f"{user_url}/wait":
            probe += 1
            return CallbackResult(status=303, headers={"Location": user_url})
        else:
            assert False, f"unknown URL {str(url)}"

    return handler


@pytest.mark.asyncio
async def test_provision() -> None:
    resource_manager = ResourceManager()
    spawner = Mock(spec=Spawner)
    spawner.user = Mock(spec=User)
    spawner.user.name = "someuser"
    auth_state = {
        "uid": 1234,
        "groups": [{"name": "foo", "id": 1234}],
    }
    spawner.user.get_auth_state.return_value = auth_state

    commission_url = "https://data.example.com/moneypenny/users"
    status_url = "https://data.example.com/moneypenny/users/someuser"
    wait_url = "https://data.example.com/moneypenny/users/someuser/wait"
    with aioresponses() as m:
        handler = build_handler(
            "someuser", 1234, [{"name": "foo", "id": 1234}]
        )
        m.post(commission_url, callback=handler)
        m.get(status_url, callback=handler, repeat=True)
        m.get(wait_url, callback=handler)
        await resource_manager.provisioner.provision_homedir(spawner)


@pytest.mark.asyncio
async def test_no_gids() -> None:
    resource_manager = ResourceManager()
    spawner = Mock(spec=Spawner)
    spawner.user = Mock(spec=User)
    spawner.user.name = "someuser"
    auth_state = {
        "uid": 1234,
        "groups": [{"name": "foo"}],
    }
    spawner.user.get_auth_state.return_value = auth_state

    commission_url = "https://data.example.com/moneypenny/users"
    status_url = "https://data.example.com/moneypenny/users/someuser"
    wait_url = "https://data.example.com/moneypenny/users/someuser/wait"
    with aioresponses() as m:
        handler = build_handler("someuser", 1234, [])
        m.post(commission_url, callback=handler)
        m.get(status_url, callback=handler, repeat=True)
        m.get(wait_url, callback=handler)
        await resource_manager.provisioner.provision_homedir(spawner)
