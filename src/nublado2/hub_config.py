# """Configuration definition."""

__all__ = ["HubConfig"]

import os

from jupyterhub.app import JupyterHub
from traitlets.config import LoggingConfigurable

from .hooks import NubladoHooks
from .nublado_config import NubladoConfig


class HubConfig(LoggingConfigurable):
    def configure(self, c: JupyterHub) -> None:
        self.log.info("Configuring JupyterHub Nublado2 style")
        self.log.debug(f"JupyterHub configuration starting as: {c}")

        nc = NubladoConfig().get()
        self.log.debug(f"Nublado Config is:\n{nc}")

        c.JupyterHub.hub_connect_url = self._get_hub_connect_url()

        # Setup hooks
        hooks = NubladoHooks()
        c.Spawner.pre_spawn_hook = hooks.pre_spawn
        c.Spawner.post_stop_hook = hooks.post_stop
        c.Spawner.options_form = hooks.show_options
        c.Spawner.options_from_form = hooks.options_from_form

        c.KubeSpawner.enable_user_namespaces = True

        # This is put in the lab pod, and tells kubernetes to
        # use all the key: values found in the lab-environment
        # configmap as environment variables for the lab
        # container.  This configmap is in the user namespace
        # and defined in nublado yaml's user_resources section.
        c.KubeSpawner.extra_container_config = {
            "envFrom": [{"configMapRef": {"name": "lab-environment"}}]
        }

        # If the image is prepulled, this will be fast.  If it isn't...
        # sure, it would be nice if images, once tagged and pushed were
        # immutable, but they're not.  T&S in particular occasionally
        # requests rebuilds, and experimental builds often go through
        # many iterations.
        c.KubeSpawner.image_pull_policy = "Always"

        self.log.info("JupyterHub configuration complete")
        self.log.debug(f"JupyterHub configuration is now: {c}")

    def _get_hub_connect_url(self) -> str:
        ns_file = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"

        with open(ns_file) as f:
            namespace = f.read().strip()
            port = os.environ["HUB_SERVICE_PORT"]
            return f"http://hub.{namespace}:{port}"
