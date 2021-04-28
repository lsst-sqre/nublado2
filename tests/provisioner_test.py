"""Tests for the Provisioner class."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import pytest
from aioresponses import CallbackResult, aioresponses
from jupyterhub.spawner import Spawner
from jupyterhub.user import User

from nublado2.resourcemgr import ResourceManager

if TYPE_CHECKING:
    from typing import Any, AsyncGenerator, Callable, Dict, List, Union


@pytest.fixture(autouse=True)
async def config_mock() -> AsyncGenerator:
    """Use a mock NubladoConfig object."""
    with patch("nublado2.resourcemgr.NubladoConfig") as mock:
        mock.return_value = MagicMock()
        mock.return_value.base_url = "https://data.example.com/"
        mock.return_valid.gafaelfawr_token = "admin-token"
        with patch("nublado2.provisioner.NubladoConfig") as mock:
            mock.return_value = MagicMock()
            mock.return_value.base_url = "https://data.example.com/"
            yield mock.return_value


def build_handler(
    username: str,
    uid: int,
    groups: List[Dict[str, Union[str, int]]],
    *,
    count: int,
) -> Callable[..., CallbackResult]:
    probe = 0

    def handler(url: str, **kwargs: Any) -> CallbackResult:
        if str(url) == "https://data.example.com/moneypenny/commission":
            assert kwargs["json"] == {
                "username": username,
                "uid": uid,
                "groups": groups,
            }
            return CallbackResult(status=202)
        elif str(url) == f"https://data.example.com/moneypenny/{username}":
            nonlocal probe
            probe += 1
            if probe == count:
                return CallbackResult(status=200)
            elif probe > count:
                return CallbackResult(status=404)
            else:
                return CallbackResult(status=202)
        else:
            assert False, f"unknown URL {str(url)}"

    return handler


@pytest.mark.asyncio
async def test_provision() -> None:
    with patch("nublado2.resourcemgr.config"):
        resource_manager = ResourceManager()

    spawner = Mock(spec=Spawner)
    spawner.user = Mock(spec=User)
    spawner.user.name = "someuser"
    spawner.user.get_auth_state.return_value = {
        "uid": 1234,
        "groups": [{"name": "foo", "id": 1234}],
    }

    commission_url = "https://data.example.com/moneypenny/commission"
    status_url = "https://data.example.com/moneypenny/someuser"
    with aioresponses() as m:
        handler = build_handler(
            "someuser", 1234, [{"name": "foo", "id": 1234}], count=2
        )
        m.post(commission_url, callback=handler)
        m.get(status_url, callback=handler, repeat=True)
        await resource_manager.provisioner.provision_homedir(spawner)
