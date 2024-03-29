"""Spawn and delete Kubernetes resources other than the pod."""
from __future__ import annotations

import asyncio
from functools import partial
from io import StringIO
from typing import TYPE_CHECKING

from jinja2 import Template
from jupyterhub.utils import exponential_backoff
from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException
from kubernetes_asyncio.utils import create_from_dict
from kubespawner.clients import shared_client
from ruamel.yaml import YAML
from traitlets.config import LoggingConfigurable

from nublado2.crdparser import CRDParser
from nublado2.nublado_config import NubladoConfig
from nublado2.provisioner import Provisioner

if TYPE_CHECKING:
    from typing import Any, Dict

    from jupyterhub.kubespawner import KubeSpawner

    from nublado2.selectedoptions import SelectedOptions


class ResourceManager(LoggingConfigurable):
    """Create additional Kubernetes resources when spawning labs.

    This is conceptually a subclass of KubeSpawner but it's patched in via
    hooks rather than as a proper subclass.  It creates (or deletes) all of
    the other resources we want to create for a lab pod, and then delegates
    creation of the pod itself to KubeSpawner.

    This class makes extensive use of KubeSpawner internals to avoid
    reimplementing the wheel and to work nicely with KubeSpawner and its
    concurrency model.
    """

    def __init__(self) -> None:
        self.nublado_config = NubladoConfig()
        self.provisioner = Provisioner()
        self.yaml = YAML()
        self.yaml.indent(mapping=2, sequence=4, offset=2)

    async def create_user_resources(
        self, spawner: KubeSpawner, options: SelectedOptions
    ) -> None:
        """Create the user resources for this spawning session."""
        await self.provisioner.provision_homedir(spawner)
        try:
            await exponential_backoff(
                partial(
                    self._wait_for_namespace_deletion,
                    spawner,
                ),
                f"Namespace {spawner.namespace} still being deleted",
                timeout=spawner.k8s_api_request_retry_timeout,
            )
            await self._create_kubernetes_resources(spawner, options)
        except Exception:
            self.log.exception("Exception creating user resource!")
            raise

    async def delete_user_resources(
        self, spawner: KubeSpawner, namespace: str
    ) -> None:
        """Clean up a Jupyter lab by deleting the whole namespace.

        It's easier to do this than try to make a list of resources to delete,
        especially when new things may be dynamically created outside of the
        hub, like dask.
        """
        # It's a post-stop hook, so the spawner API client will exist.
        await exponential_backoff(
            partial(self._wait_for_namespace_deletion, spawner),
            f"Namespace {namespace} still being deleted",
            timeout=spawner.k8s_api_request_retry_timeout,
        )

    async def _create_lab_environment_configmap(
        self, spawner: KubeSpawner, template_values: Dict[str, Any]
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
                labels=spawner.extra_labels,
            ),
            data=environment,
        )
        await exponential_backoff(
            partial(spawner._make_create_resource_request, "config_map", body),
            f"Could not create ConfigMap {spawner.namespace}/lab-environment",
            timeout=spawner.k8s_api_request_retry_timeout,
        )

    async def _create_kubernetes_resources(
        self, spawner: KubeSpawner, options: SelectedOptions
    ) -> None:
        custom_api = shared_client("CustomObjectsApi")
        template_values = await self._build_template_values(spawner, options)

        # Generate the list of additional user resources from the template.
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
            resource["metadata"]["labels"] = spawner.extra_labels

            # Custom resources cannot be created by create_from_dict:
            # https://github.com/kubernetes-client/python/issues/740
            #
            # Detect those from the apiVersion field and handle them
            # specially.
            api_version = resource["apiVersion"]
            if "." in api_version and ".k8s.io/" not in api_version:
                crd_parser = CRDParser.from_crd_body(resource)
                await asyncio.wait_for(
                    custom_api.create_namespaced_custom_object(
                        body=resource,
                        group=crd_parser.group,
                        version=crd_parser.version,
                        namespace=spawner.namespace,
                        plural=crd_parser.plural,
                    ),
                    spawner.k8s_api_request_timeout,
                )
            else:
                await asyncio.wait_for(
                    create_from_dict(spawner.api.api_client, resource),
                    spawner.k8s_api_request_timeout,
                )

        # Construct the lab environment ConfigMap.  This is constructed from
        # configuration settings and doesn't use a resource template like
        # other resources.  This has to be done last, becuase the namespace is
        # created from the user resources template.
        await self._create_lab_environment_configmap(spawner, template_values)

    async def _build_dask_template(self, spawner: KubeSpawner) -> str:
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
            spawner.api.api_client.sanitize_for_serialization(dask_template),
            dask_yaml_stream,
        )
        return dask_yaml_stream.getvalue()

    async def _build_template_values(
        self, spawner: KubeSpawner, options: SelectedOptions
    ) -> Dict[str, Any]:
        """Construct the template variables for Jinja templating."""
        auth_state = await spawner.user.get_auth_state()
        groups = auth_state["groups"]

        # Build a comma-separated list of groups used to populate the
        # /etc/groups file.  Only groups with GIDs can be added, so skip
        # groups without GIDs.
        #
        # Example: group1:1000,group2:1001,group3:1002
        external_groups = ",".join(
            [f'{g["name"]}:{g["id"]}' for g in groups if "id" in g]
        )

        # Define the template variables.
        template_values = {
            "user_namespace": spawner.namespace,
            "user": spawner.user.name,
            "uid": auth_state["uid"],
            "gid": auth_state.get("gid"),
            "token": auth_state["token"],
            "groups": groups,
            "external_groups": external_groups,
            "base_url": self.nublado_config.base_url,
            "dask_yaml": await self._build_dask_template(spawner),
            "options": options,
            "nublado_base_url": spawner.hub.base_url,
            "butler_secret_path": self.nublado_config.butler_secret_path,
            "pull_secret_path": self.nublado_config.pull_secret_path,
        }
        self.log.debug(f"Template values={template_values}")
        return template_values

    async def _wait_for_namespace_deletion(self, spawner: KubeSpawner) -> bool:
        """Waits for the user's namespace to be deleted.

        If the namespace exists but has not been marked for deletion, try to
        delete it.  If we're spawning a new lab while the namespace still
        exists, that means something has gone wrong with the user's lab and
        there's nothing salvagable.

        Returns
        -------
        done : `bool`
            `True` if the namespace has been deleted, `False` if it still
            exists
        """
        api = shared_client("CoreV1Api")
        try:
            ns_name = spawner.namespace
            # Note that this is not safe to run if you aren't using
            # user namespaces.  Check that:
            assert spawner.enable_user_namespaces
            # Let's do a further check for paranoia.  We will assume that
            # a user namespace will be of the form <hub-namespace>-<something>
            # This is true for Rubin user namespaces, but might not be
            # universally.
            #
            # If opening the ns_path file fails, it means we are not running
            # in a namespace with service accounts enabled, in which case
            # we definitely want to let the exception crash the process.
            ns_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
            with open(ns_path) as f:
                hub_ns = f.read().strip()
            assert ns_name.startswith(f"{hub_ns}-")

            namespace = await asyncio.wait_for(
                api.read_namespace(ns_name),
                spawner.k8s_api_request_timeout,
            )
            if namespace.status.phase != "Terminating":
                self.log.info(f"Deleting namespace {ns_name}")
                await asyncio.wait_for(
                    api.delete_namespace(ns_name),
                    spawner.k8s_api_request_timeout,
                )
            return False
        except asyncio.TimeoutError:
            return False
        except ApiException as e:
            if e.status == 404:
                return True
            raise
