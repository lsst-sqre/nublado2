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

    async def create_user_resources(self, spawner: Spawner) -> None:
        try:
            auth_state = await spawner.user.get_auth_state()
            self.log.debug(f"Auth state={auth_state}")

            groups = auth_state["groups"]

            # Build a comma separated list of group:gid
            # ex: group1:1000,group2:1001,group3:1002
            external_groups = ",".join(
                [f'{g["name"]}:{g["id"]}' for g in groups]
            )

            pod_manifest = await spawner.get_pod_manifest()

            # Here we make a few mangles to the jupyter pod manifest
            # before stuffing it into configmaps.  This will end up
            # being used for the pod template for dask.
            pod_manifest.metadata.name = None
            pod_manifest.metadata.namespace = None
            pod_manifest.spec.containers[0].ports = None
            pod_manifest.spec.containers[0].args = [
                "/opt/lsst/software/jupyterlab/provisionator.bash"
            ]
            pod_manifest.spec.containers[0].env.append(
                client.models.V1EnvVar(name="DASK_WORKER", value="TRUE")
            )

            # This will take the python model names and transform
            # them to the names kubernetes expects, which to_dict
            # alone doesn't.
            dask_yaml = yaml.dump(
                self.k8s_api.sanitize_for_serialization(pod_manifest)
            )

            template_values = {
                "user_namespace": spawner.namespace,
                "user": spawner.user.name,
                "uid": auth_state["uid"],
                "token": auth_state["token"],
                "groups": groups,
                "external_groups": external_groups,
                "base_url": NubladoConfig().get().get("base_url"),
                "dask_yaml": dask_yaml,
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

    def delete_user_resources(self, namespace: str) -> None:
        self.k8s_client.delete_namespace(name=namespace)
