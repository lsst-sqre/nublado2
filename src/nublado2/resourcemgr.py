from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

import aiohttp
from jinja2 import Template
from kubernetes import client, config
from kubernetes.utils import create_from_dict
from ruamel.yaml import YAML
from traitlets.config import LoggingConfigurable

from nublado2.crdparser import CRDParser
from nublado2.nublado_config import NubladoConfig
from nublado2.provisioner import Provisioner

if TYPE_CHECKING:
    from typing import Any, Dict

    from jupyterhub.spawner import Spawner

    from nublado2.selectedoptions import SelectedOptions


class ResourceManager(LoggingConfigurable):
    # These k8s clients don't copy well with locks, connection,
    # pools, locks, etc.  Copying seems to happen under the hood of the
    # LoggingConfigurable base class, so just have them be class variables.
    # Should be safe to share these, and better to have fewer of them.
    k8s_api = client.ApiClient()
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
        self.yaml = YAML()
        self.yaml.indent(mapping=2, sequence=4, offset=2)

    async def create_user_resources(
        self, spawner: Spawner, options: SelectedOptions
    ) -> None:
        """Create the user resources for this spawning session."""
        await self.provisioner.provision_homedir(spawner)
        try:
            await self._create_kubernetes_resources(spawner, options)
        except Exception:
            self.log.exception("Exception creating user resource!")
            raise

    def _create_lab_environment_configmap(
        self, spawner: Spawner, template_values: Dict[str, Any]
    ) -> None:
        """Create the ConfigMap that holds environment settings for the lab."""
        environment = {}
        for variable, template in self.nublado_config.lab_environment.items():
            value = Template(template).render(template_values)
            environment[variable] = value

        self.log.debug(f"Creating environment ConfigMap with {environment}")
        body = client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            metadata=client.V1ObjectMeta(
                name="lab-environment",
                namespace=spawner.namespace,
                annotations=spawner.extra_annotations,
                labels=spawner.common_labels,
            ),
            data=environment,
        )
        self.k8s_client.create_namespaced_config_map(spawner.namespace, body)

    async def _create_kubernetes_resources(
        self, spawner: Spawner, options: SelectedOptions
    ) -> None:
        template_values = await self._build_template_values(spawner, options)

        # Construct the lab environment ConfigMap.  This is constructed from
        # configuration settings and doesn't use a resource template like
        # other resources.
        self._create_lab_environment_configmap(spawner, template_values)

        # Generate the list of additional user resources from the template.
        self.log.debug("Template:")
        self.log.debug(self.nublado_config.user_resources_template)
        t = Template(self.nublado_config.user_resources_template)
        templated_user_resources = t.render(template_values)
        self.log.debug("Generated user resources:")
        self.log.debug(templated_user_resources)
        resources = self.yaml.load(templated_user_resources)

        # Add in the standard labels and annotations common to every resource
        # and create the resources.
        for resource in resources:
            if "metadata" not in resource:
                resource["metadata"] = {}
            resource["metadata"]["annotations"] = spawner.extra_annotations
            resource["metadata"]["labels"] = spawner.common_labels

            # Custom resources cannot be created by create_from_dict:
            # https://github.com/kubernetes-client/python/issues/740
            #
            # Detect those from the apiVersion field and handle them
            # specially.
            api_version = resource["apiVersion"]
            if "." in api_version and ".k8s.io/" not in api_version:
                crd_parser = CRDParser.from_crd_body(resource)
                self.custom_api.create_namespaced_custom_object(
                    body=resource,
                    group=crd_parser.group,
                    version=crd_parser.version,
                    namespace=spawner.namespace,
                    plural=crd_parser.plural,
                )
            else:
                create_from_dict(self.k8s_api, resource)

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
        dask_yaml_stream = StringIO()
        self.yaml.dump(
            self.k8s_api.sanitize_for_serialization(dask_template),
            dask_yaml_stream,
        )
        return dask_yaml_stream.getvalue()

    async def _build_template_values(
        self, spawner: Spawner, options: SelectedOptions
    ) -> Dict[str, Any]:
        """Construct the template variables for Jinja templating."""
        auth_state = await spawner.user.get_auth_state()
        self.log.debug(f"Auth state={auth_state}")
        groups = auth_state["groups"]

        # Build a comma separated list of group:gid
        # ex: group1:1000,group2:1001,group3:1002
        external_groups = ",".join([f'{g["name"]}:{g["id"]}' for g in groups])

        # Define the template variables.
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
            "nublado_base_url": spawner.hub.base_url,
            "butler_secret_path": self.nublado_config.butler_secret_path,
        }
        self.log.debug(f"Template values={template_values}")
        return template_values

    def delete_user_resources(self, namespace: str) -> None:
        """Clean up a jupyterlab by deleting the whole namespace.

        The reason is it's easier to do this than try to make a list
        of resources to delete, especially when new things may be
        dynamically created outside of the hub, like dask."""
        self.k8s_client.delete_namespace(name=namespace)
