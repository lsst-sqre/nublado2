import yaml
from jinja2 import Template
from jupyterhub.spawner import Spawner
from kubernetes import client, config
from kubernetes.utils import create_from_dict
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
            gids = auth_state["gids"]

            # Build a comma separated list of group:gid
            # ex: group1:1000,group2:1001,group3:1002
            external_groups = ",".join(
                [f"{group}:{gid}" for group, gid in zip(groups, gids)]
            )

            template_values = {
                "user_namespace": spawner.namespace,
                "user": spawner.user.name,
                "uid": auth_state["uid"],
                "token": auth_state["token"],
                "groups": groups,
                "gids": gids,
                "external_groups": external_groups,
                "base_url": NubladoConfig().get().get("base_url"),
            }

            self.log.debug(f"Template values={template_values}")
            resources = NubladoConfig().get().get("user_resources", [])
            for r in resources:
                t = Template(yaml.dump(r))
                templated_yaml = t.render(template_values)
                self.log.debug(f"Creating resource:\n{templated_yaml}")
                templated_resource = yaml.load(templated_yaml, yaml.SafeLoader)
                create_from_dict(self.k8s_api, templated_resource)
        except Exception:
            self.log.exception("Exception creating user resource!")
            raise

    def delete_user_resources(self, namespace: str) -> None:
        self.k8s_client.delete_namespace(name=namespace)
