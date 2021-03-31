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

            nc = NubladoConfig().get()
            groups = auth_state["groups"]

            # Build a comma separated list of group:gid
            # ex: group1:1000,group2:1001,group3:1002
            external_groups = ",".join(
                [f'{g["name"]}:{g["id"]}' for g in groups]
            )

            # Retrieve image tag and corresponding hash (if any)
            # These come back from the options form as one-item lists
            img_list_str = spawner.user_options["image_list"][0]
            img_dropdown_str = spawner.user_options["image_dropdown"][0]
            image_info = ImageInfo(img_list_str, img_dropdown_str)
            img_tag = image_info.get_tag()
            img_hash = image_info.get_hash()
            img_desc = image_info.get_desc()

            template_values = {
                "user_namespace": spawner.namespace,
                "user": spawner.user.name,
                "uid": auth_state["uid"],
                "token": auth_state["token"],
                "groups": groups,
                "external_groups": external_groups,
                "base_url": nc.get("base_url"),
                "dask_yaml": await self._build_dask_template(spawner),
                "auto_repo_urls": nc.get("auto_repo_urls"),
                "image_tag": img_tag,
                "image_hash": img_hash,
                "image_desc": img_desc,
            }

            self.log.debug(f"Template values={template_values}")
            resources = nc.get("user_resources", [])
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
        nc = NubladoConfig().get()
        hc = self.http_client
        base_url = nc.get("base_url")
        uname = spawner.user.name
        auth_state = await spawner.user.get_auth_state()
        dossier = {
            "username": uname,
            "uid": int(auth_state["uid"]),
            "groups": auth_state["groups"],
        }
        token = await self._mint_admin_token()
        endpt = f"{base_url}/moneypenny/commission"
        auth = {"Authorization": f"Bearer {token}"}
        self.log.debug(f"Posting dossier {dossier} to {endpt}")
        resp = await hc.post(endpt, json=dossier, headers=auth)
        self.log.debug(f"POST got {resp.status}")
        resp.raise_for_status()
        route = f"{base_url}/moneypenny/{uname}"
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
        nc = NubladoConfig().get()
        template_file = os.path.join(
            os.path.dirname(__file__), "static/moneypenny-jwt-template.json"
        )
        base_url = nc.get("base_url")
        signing_key_path = nc.get("signing_key_path")
        assert isinstance(signing_key_path, str)
        with open(signing_key_path, "r") as f:
            signing_key = f.read()
            current_time = int(
                datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
            )
        with open(template_file, "r") as f:
            token_template = Template(f.read())
        token_data = {
            "environment_url": base_url,
            "username": "moneypenny",
            "uidnumber": 1007,
            "issue_time": current_time,
            "expiration_time": current_time + 300,
        }
        rendered_token = token_template.render(token_data)
        token_dict = json.loads(rendered_token)
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


class ImageInfo(object):
    """Take the strings that come out of the image form as constructors:
    list form first, and dropdown form second.

    These strings will be pipe-separated fields whose contents are:
    * Docker image spec
    * Human-friendly image description
    * Image hash, if known, or the empty string.

    If the image was chosen from the dropdown, the first field of
    list_image_info will be "image_from_dropdown", and that will
    signal that we use dropdown_image_info to populate the object
    rather than list_image_info.

    This will create an ImageInfo object with methods to get to get the image
    spec, tag, description, and hash.

    If not known, the hash will be returned as the empty string.

    """

    def __init__(self, list_image_info: str, dropdown_image_info: str) -> None:
        image_fields = list_image_info.split("|")
        assert len(image_fields) == 3
        if image_fields[0] == "image_from_dropdown":
            image_fields = dropdown_image_info.split("|")
            assert len(image_fields) == 3
        self.image_spec = image_fields[0]
        self.image_desc = image_fields[1]
        self.image_hash = image_fields[2]
        # The tag is what's after the colon in the image spec
        self.image_tag = self.image_spec.split(":")[-1]

    def get_spec(self) -> str:
        """Return the Docker image spec."""
        return self.image_spec

    def get_desc(self) -> str:
        """Return the human-friendly image description."""
        return self.image_desc

    def get_hash(self) -> str:
        """Return the image hash, if known, or empty string."""
        return self.image_hash

    def get_tag(self) -> str:
        """Return the image tag."""
        return self.image_tag
