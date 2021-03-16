import asyncio
import datetime
import json
import math
import os
from string import Template as strTemplate
from typing import Any, Dict, Optional

import aiohttp
import jwt
from jinja2 import Template
from jupyterhub.spawner import Spawner
from kubernetes import client, config
from kubernetes.utils import create_from_dict
from ruamel import yaml
from ruamel.yaml import RoundTripDumper, RoundTripLoader
from traitlets.config import LoggingConfigurable

from nublado2.nublado_config import NubladoConfig

config.load_incluster_config()


class ResourceManager(LoggingConfigurable):
    # These k8s clients don't copy well with locks, connection,
    # pools, locks, etc.  Copying seems to happen under the hood of the
    # LoggingConfigurable base class, so just have them be class variables.
    # Should be safe to share these, and better to have fewer of them.
    k8s_api = client.api_client.ApiClient()
    k8s_client = client.CoreV1Api()
    # Same for the http_client: all the hub requests will have the same
    #  authorization needs
    http_client = aiohttp.ClientSession()

    async def create_user_resources(self, spawner: Spawner) -> None:
        """Create the user resources for this spawning session."""
        try:
            await self._request_homedir_provisioning(spawner)
        except Exception:
            self.log.exception("Exception requesting homedir provisioning!")
            raise
        try:
            auth_state = await spawner.user.get_auth_state()
            self.log.debug(f"Auth state={auth_state}")

            groups = auth_state["groups"]

            # Build a comma separated list of group:gid
            # ex: group1:1000,group2:1001,group3:1002
            external_groups = ",".join(
                [f'{g["name"]}:{g["id"]}' for g in groups]
            )

            template_values = {
                "user_namespace": spawner.namespace,
                "user": spawner.user.name,
                "uid": auth_state["uid"],
                "token": auth_state["token"],
                "groups": groups,
                "external_groups": external_groups,
                "base_url": NubladoConfig().get().get("base_url"),
                "dask_yaml": await self._build_dask_template(spawner),
            }

            self.log.debug(f"Template values={template_values}")
            resources = NubladoConfig().get().get("user_resources", [])
            for r in resources:
                t_yaml = yaml.dump(r, Dumper=RoundTripDumper)
                self.log.debug(f"Resource template:\n{t_yaml}")
                t = Template(t_yaml)
                templated_yaml = t.render(template_values)
                self.log.debug(f"Creating resource:\n{templated_yaml}")
                templated_resource = yaml.load(
                    templated_yaml, Loader=RoundTripLoader
                )
                create_from_dict(self.k8s_api, templated_resource)
        except Exception:
            self.log.exception("Exception creating user resource!")
            raise

    async def _request_homedir_provisioning(self, spawner: Spawner) -> None:
        """Submit a request for provisioning via Moneypenny."""
        nc = NubladoConfig()
        hc = self.http_client
        base_url: str = nc.get().get("base_url") or "http://localhost:8080"
        uname = spawner.user.name
        auth_state = await spawner.user.get_auth_state()
        dossier = await self._make_dossier(uname, auth_state)
        token = await self._mint_admin_token(base_url, None)
        mp_ep = f"{base_url}/moneypenny"
        endpt = f"{mp_ep}/commission"
        auth = {"Authorization": f"Bearer {token}"}
        self.log.debug(f"Posting dossier {dossier} to {endpt}")
        resp = await hc.post(endpt, json=dossier, headers=auth)
        self.log.debug(f"POST got {resp.status}")
        resp.raise_for_status()
        expiry = datetime.datetime.now() + datetime.timedelta(seconds=300)
        count = 0
        route = f"{mp_ep}/{uname}"
        while datetime.datetime.now() < expiry:
            count += 1
            self.log.debug(f"Checking Moneypenny status at {route}: #{count}")
            resp = await hc.get(f"{route}", headers=auth)
            status = resp.status
            self.log.debug(f"Moneypenny status: {status}")
            if status == 200 or 404:
                return
            if status != 202:
                raise RuntimeError(
                    f"Unexpected status from Moneypenny: {status}"
                )
            await asyncio.sleep(int(math.log(count)))
        raise RuntimeError("Moneypenny timed out")

    async def _make_dossier(
        self, name: str, auth_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        dossier = {
            "username": name,
            "uid": int(auth_state["uid"]),
            "groups": auth_state["groups"],
        }
        self.log.debug(f"Dossier: {dossier}")
        return dossier

    async def _mint_admin_token(
        self, base_url: str, signing_key_path: Optional[str]
    ) -> str:
        """Allowing specification of the signing key makes testing easier."""
        template_file = os.path.join(
            os.path.dirname(__file__), "static/moneypenny-jwt-template.json"
        )
        with open(template_file, "r") as f:
            token_template = strTemplate(f.read())
        if not signing_key_path:
            signing_key_path = "/etc/keys/signing_key.pem"
        with open(signing_key_path, "r") as f:
            signing_key = f.read()
            current_time = int(
                datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
            )
        token_data = {
            "environment_url": base_url,
            "username": "moneypenny",
            "uidnumber": 1007,
            "issue_time": current_time,
            "expiration_time": current_time + 300,
        }
        token_dict = json.loads(token_template.substitute(token_data))
        token = jwt.encode(
            token_dict,
            key=signing_key,
            headers={"kid": "reissuer"},
            algorithm="RS256",
        )
        return token

    async def _build_dask_template(self, spawner: Spawner) -> str:
        """Build a template for dask workers from the jupyter pod manifest."""
        dask_template = await spawner.get_pod_manifest()

        # Here we make a few mangles to the jupyter pod manifest
        # before using it for templating.  This will end up
        # being used for the pod template for dask.
        # Unset the name of the container, to let dask make the container
        # names, otherwise you'll get an obtuse error from k8s about not
        # being able to create the container.
        dask_template.metadata.name = None

        # This is an argument to the provisioning script to signal it
        # as a dask worker.
        dask_template.spec.containers[0].env.append(
            client.models.V1EnvVar(name="DASK_WORKER", value="TRUE")
        )

        # This will take the python model names and transform
        # them to the names kubernetes expects, which to_dict
        # alone doesn't.
        dask_yaml = yaml.dump(
            self.k8s_api.sanitize_for_serialization(dask_template)
        )

        if not dask_yaml:
            # This is mostly to help with the typing.
            raise Exception("Dask template ended up empty.")
        else:
            return dask_yaml

    def delete_user_resources(self, namespace: str) -> None:
        """Clean up a jupyterlab by deleting the whole namespace.

        The reason is it's easier to do this than try to make a list
        of resources to delete, especially when new things may be
        dynamically created outside of the hub, like dask."""
        self.k8s_client.delete_namespace(name=namespace)
