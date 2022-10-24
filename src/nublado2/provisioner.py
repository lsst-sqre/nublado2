"""Home directory provisioning."""

from __future__ import annotations

from urllib.parse import urljoin

from aiohttp import ClientTimeout
from jupyterhub.spawner import Spawner
from tornado import web
from traitlets.config import LoggingConfigurable

from nublado2.http import get_session
from nublado2.nublado_config import NubladoConfig

__all__ = ["Provisioner"]


class Provisioner(LoggingConfigurable):
    """Provision home directories using the moneypenny service."""

    def __init__(self) -> None:
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
        token = self.nublado_config.gafaelfawr_token

        # Only include groups with GIDs.  Provisioning can't do anything with
        # the ones that don't have GIDs, and currently the model doesn't allow
        # them.
        groups = [g for g in auth_state["groups"] if "id" in g]

        # Start the provisioning request.
        dossier = {
            "username": spawner.user.name,
            "uid": int(auth_state["uid"]),
            "groups": groups,
        }
        provision_url = urljoin(base_url, "moneypenny/users")
        session = await get_session()
        self.log.debug(f"Posting dossier {dossier} to {provision_url}")
        r = await session.post(
            provision_url,
            json=dossier,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.log.debug(f"POST got {r.status}")
        r.raise_for_status()

        # Wait until the work has finished.
        data = await r.json()
        if data["status"] != "active":
            return await self._wait_for_provision(spawner.user.name)

    async def _wait_for_provision(self, username: str) -> None:
        """Wait for provisioning to complete."""
        base_url = self.nublado_config.base_url
        status_url = urljoin(base_url, f"moneypenny/users/{username}/wait")
        token = self.nublado_config.gafaelfawr_token
        session = await get_session()

        r = await session.get(
            status_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=ClientTimeout(total=300),
        )
        self.log.debug(f"Moneypenny {status_url} status: {r.status}")
        if r.status == 200:
            data = await r.json()
            if data["status"] != "active":
                status = data["status"]
                raise web.HTTPError(500, f"Moneypenny reports status {status}")
        else:
            r.raise_for_status()
