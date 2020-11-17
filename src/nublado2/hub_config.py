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
        c.JupyterHub.spawner_class = "nublado2.spawner.NubladoSpawner"

        # Setup hooks
        hooks = NubladoHooks()
        c.Spawner.pre_spawn_hook = hooks.pre_spawn
        c.Spawner.post_stop_hook = hooks.post_stop
        c.Spawner.options_form = hooks.show_options

        c.KubeSpawner.enable_user_namespaces = True

        self.log.info("JupyterHub configuration complete")
        self.log.debug(f"JupyterHub configuration is now: {c}")

    def _get_hub_connect_url(self) -> str:
        ns_file = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"

        with open(ns_file) as f:
            namespace = f.read().strip()
            port = os.environ["HUB_SERVICE_PORT"]
            return f"http://hub.{namespace}:{port}"
