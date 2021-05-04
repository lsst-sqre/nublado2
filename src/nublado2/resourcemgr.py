import aiohttp
from jinja2 import Template
from jupyterhub.spawner import Spawner
from kubernetes import client, config
from kubernetes.utils import create_from_dict
from ruamel import yaml
from ruamel.yaml import RoundTripLoader
from traitlets.config import LoggingConfigurable

from nublado2.crdparser import CRDParser
from nublado2.nublado_config import NubladoConfig
from nublado2.provisioner import Provisioner
from nublado2.selectedoptions import SelectedOptions


class ResourceManager(LoggingConfigurable):
    # These k8s clients don't copy well with locks, connection,
    # pools, locks, etc.  Copying seems to happen under the hood of the
    # LoggingConfigurable base class, so just have them be class variables.
    # Should be safe to share these, and better to have fewer of them.
    k8s_api = client.api_client.ApiClient()
    custom_api = client.CustomObjectsApi()
    k8s_client = client.CoreV1Api()

    def __init__(self) -> None:
        config.load_incluster_config()
        self.nublado_config = NubladoConfig()
        token = self.nublado_config.gafaelfawr_token
        self.http_client = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {token}"}
        )
        self.provisioner = Provisioner(self.http_client)

    async def create_user_resources(
        self, spawner: Spawner, options: SelectedOptions
    ) -> None:
        """Create the user resources for this spawning session."""
        await self.provisioner.provision_homedir(spawner)

        try:
            auth_state = await spawner.user.get_auth_state()
            self.log.debug(f"Auth state={auth_state}")
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
                "base_url": self.nublado_config.base_url,
                "dask_yaml": await self._build_dask_template(spawner),
                "options": options,
                "labels": spawner.common_labels,
                "annotations": spawner.extra_annotations,
                "nublado_base_url": spawner.hub.base_url,
                "butler_secret_path": self.nublado_config.butler_secret_path,
                "lab_environment": self.nublado_config.lab_environment,
            }

            self.log.debug(f"Template values={template_values}")
            self.log.debug("Template:")
            self.log.debug(self.nublado_config.user_resources_template)
            t = Template(self.nublado_config.user_resources_template)
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
            ct = Template(self.nublado_config.custom_resources_template)
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
