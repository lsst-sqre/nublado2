import datetime
import json
import os

import aiohttp
import jwt
from jinja2 import Template
from jupyterhub.spawner import Spawner
from jupyterhub.utils import exponential_backoff
from kubernetes import client, config
from kubernetes.utils import create_from_dict
from ruamel import yaml
from ruamel.yaml import RoundTripLoader
from traitlets.config import LoggingConfigurable

from nublado2.crdparser import CRDParser
from nublado2.nublado_config import NubladoConfig
from nublado2.selectedoptions import SelectedOptions

config.load_incluster_config()


class ResourceManager(LoggingConfigurable):
    # These k8s clients don't copy well with locks, connection,
    # pools, locks, etc.  Copying seems to happen under the hood of the
    # LoggingConfigurable base class, so just have them be class variables.
    # Should be safe to share these, and better to have fewer of them.
    k8s_api = client.api_client.ApiClient()
    custom_api = client.CustomObjectsApi()
    k8s_client = client.CoreV1Api()
    # Same for the http_client: all the hub requests will have the same
    #  authorization needs
    http_client = aiohttp.ClientSession()

    async def create_user_resources(
        self, spawner: Spawner, options: SelectedOptions
    ) -> None:
        """Create the user resources for this spawning session."""
        try:
            await self._request_homedir_provisioning(spawner)
        except Exception:
            self.log.exception("Exception requesting homedir provisioning!")
            raise
        try:
            auth_state = await spawner.user.get_auth_state()
            self.log.debug(f"Auth state={auth_state}")

            nc = NubladoConfig()
            groups = auth_state["groups"]

            # Build a comma separated list of group:gid
            # ex: group1:1000,group2:1001,group3:1002
            external_groups = ",".join(
                [f'{g["name"]}:{g["id"]}' for g in groups]
            )

            # Retrieve image tag and corresponding hash (if any)
            # These come back from the options form as one-item lists

            template_values = {
                "user_namespace": spawner.namespace,
                "user": spawner.user.name,
                "uid": auth_state["uid"],
                "token": auth_state["token"],
                "groups": groups,
                "external_groups": external_groups,
                "base_url": nc.base_url,
                "dask_yaml": await self._build_dask_template(spawner),
                "options": options,
                "labels": spawner.common_labels,
                "annotations": spawner.extra_annotations,
                "nublado_base_url": spawner.hub.base_url,
                "butler_secret_path": nc.butler_secret_path,
            }

            self.log.debug(f"Template values={template_values}")
            self.log.debug("Template:")
            self.log.debug(nc.user_resources_template)
            t = Template(nc.user_resources_template)
            templated_user_resources = t.render(template_values)
            self.log.debug("Generated user resources:")
            self.log.debug(templated_user_resources)

            user_resources = yaml.load(
                templated_user_resources, Loader=RoundTripLoader
            )

            for r in user_resources:
                self.log.debug(f"Creating: {r}")
                create_from_dict(self.k8s_api, r)
        except Exception:
            self.log.exception("Exception creating user resource!")
            raise
        try:
            # CRDs cannot be created with create_from_dict:
            # https://github.com/kubernetes-client/python/issues/740
            ct = Template(nc.custom_resources_template)
            templated_custom_resources = ct.render(template_values)
            self.log.debug("Generated custom resources:")
            self.log.debug(templated_custom_resources)
            custom_resources = yaml.load(
                templated_custom_resources, Loader=RoundTripLoader
            )
            for cr in custom_resources:
                self.log.debug(f"Creating: {cr}")
                crd_parser = CRDParser.from_crd_body(cr)
                self.log.debug(f"CRD_Parser: {crd_parser}")
                self.custom_api.create_namespaced_custom_object(
                    body=cr,
                    group=crd_parser.group,
                    version=crd_parser.version,
                    namespace=spawner.namespace,
                    plural=crd_parser.plural,
                )
        except Exception:
            self.log.exception("Exception creating custom resource!")
            raise

    async def _request_homedir_provisioning(self, spawner: Spawner) -> None:
        """Submit a request for provisioning via Moneypenny."""
        nc = NubladoConfig()
        hc = self.http_client
        uname = spawner.user.name
        auth_state = await spawner.user.get_auth_state()
        dossier = {
            "username": uname,
            "uid": int(auth_state["uid"]),
            "groups": auth_state["groups"],
        }
        if nc.gafaelfawr_token:
            token = nc.gafaelfawr_token
        else:
            token = await self._mint_admin_token()
        endpt = f"{nc.base_url}/moneypenny/commission"
        auth = {"Authorization": f"Bearer {token}"}
        self.log.debug(f"Posting dossier {dossier} to {endpt}")
        resp = await hc.post(endpt, json=dossier, headers=auth)
        self.log.debug(f"POST got {resp.status}")
        resp.raise_for_status()
        route = f"{nc.base_url}/moneypenny/{uname}"
        count = 0

        async def _check_moneypenny_completion() -> bool:
            nonlocal count
            count += 1
            self.log.debug(f"Checking Moneypenny status at {route}: #{count}")
            resp = await hc.get(f"{route}", headers=auth)
            status = resp.status
            self.log.debug(f"Moneypenny status: {status}")
            if status == 200 or 404:
                return True
            if status != 202:
                raise RuntimeError(
                    f"Unexpected status from Moneypenny: {status}"
                )
            # Moneypenny is still working.
            return False

        await exponential_backoff(
            _check_moneypenny_completion,
            fail_message="Moneypenny did not complete.",
            timeout=300,
        )

    async def _mint_admin_token(self) -> str:
        """Create a token with exec:admin scope, signed as if Gafaelfawr had
        created it, in order to submit orders to Moneypenny.
        """
        nc = NubladoConfig()
        template_file = os.path.join(
            os.path.dirname(__file__), "static/moneypenny-jwt-template.json"
        )
        current_time = int(
            datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
        )
        with open(template_file, "r") as f:
            token_template = Template(f.read())

        token_data = {
            "environment_url": nc.base_url,
            "username": "moneypenny",
            "uidnumber": 1007,
            "issue_time": current_time,
            "expiration_time": current_time + 300,
        }
        rendered_token = token_template.render(token_data)
        token_dict = json.loads(rendered_token)
        token = jwt.encode(
            token_dict,
            key=nc.signing_key,
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
