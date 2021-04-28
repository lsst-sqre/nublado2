"""Home directory provisioning."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin

from jupyterhub.utils import exponential_backoff
from traitlets.config import LoggingConfigurable

from nublado2.nublado_config import NubladoConfig

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from jupyterhub.spawner import Spawner

__all__ = ["Provisioner"]


class Provisioner(LoggingConfigurable):
    """Provision home directories using the moneypenny service.

    Parameters
    ----------
    http_client : `aiohttp.ClientSession`
        HTTP client to use to make requests.
    """

    def __init__(self, http_client: ClientSession) -> None:
        self.http_client = http_client
        self.nublado_config = NubladoConfig()

    async def provision_homedir(self, spawner: Spawner) -> None:
        """Provision the home directory for the user.

        Parameters
        ----------
        spawner : `jupyterhub.spawner.Spawner`
            The spawner object, used to get the authentication state and other
            user metadata.
        """
        auth_state = await spawner.user.get_auth_state()
        base_url = self.nublado_config.base_url

        # Start the provisioning request.
        dossier = {
            "username": spawner.user.name,
            "uid": int(auth_state["uid"]),
            "groups": auth_state["groups"],
        }
        provision_url = urljoin(base_url, "moneypenny/commission")
        self.log.debug(f"Posting dossier {dossier} to {provision_url}")
        r = await self.http_client.post(provision_url, json=dossier)
        self.log.debug(f"POST got {r.status}")
        r.raise_for_status()

        # Use a wrapper to log the number of requests.
        count = 0

        async def _wait_wrapper() -> bool:
            nonlocal count
            count += 1
            self.log.debug(f"Checking Moneypenny status #{count}")
            return await self._wait_for_provision(spawner.user.name)

        # Run with exponential backoff and a maximum timeout of 5m.
        await exponential_backoff(
            _wait_wrapper,
            fail_message="Moneypenny did not complete",
            timeout=300,
        )

    async def _wait_for_provision(self, username: str) -> bool:
        """Wait for provisioning to complete."""
        base_url = self.nublado_config.base_url
        status_url = urljoin(base_url, f"moneypenny/{username}")
        r = await self.http_client.get(status_url)
        self.log.debug(f"Moneypenny {status_url} status: {r.status}")
        if r.status == 200 or r.status == 404:
            return True
        if r.status != 202:
            r.raise_for_status()
        return False
