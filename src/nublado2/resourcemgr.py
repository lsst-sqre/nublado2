import yaml
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

    def create_user_resources(self, user: str) -> None:
        template_values = {"user": user}

        resources = NubladoConfig().get().get("user_resources", [])
        for r in resources:
            templated_yaml = yaml.dump(r).format(**template_values)
            templated_resource = yaml.load(templated_yaml, yaml.SafeLoader)
            self.log.debug(f"Creating resource:\n{templated_yaml}")
            create_from_dict(self.k8s_api, templated_resource)

    def delete_user_resources(self, user: str) -> None:
        # TODO: the namespace should probably be cleaned up by the
        # multinamespace kubespawner, but this is how to delete the
        # namespace this way.  We might not even have to fill in this hook.
        self.k8s_client.delete_namespace(name=user)
