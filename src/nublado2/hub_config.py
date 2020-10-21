# """Configuration definition."""

__all__ = ["HubConfig"]

from jupyterhub.app import JupyterHub
from traitlets.config import LoggingConfigurable

from .nublado_config import NubladoConfig


class HubConfig(LoggingConfigurable):
    def configure(self, c: JupyterHub) -> None:
        self.log.info("Configuring JupyterHub Nublado2 style")
        self.log.debug(f"JupyterHub configuration starting as: {c}")

        nc = NubladoConfig().get()
        self.log.debug(f"Nublado Config is:\n{nc}")

        c.JupyterHub.authenticator_class = (
            "dummyauthenticator.DummyAuthenticator"
        )
        c.JupyterHub.spawner_class = "kubespawner.KubeSpawner"

        # Point to the proxy pod, which is a k8s service for the proxy.
        c.ConfigurableHTTPProxy.api_url = "http://proxy-api:8001"
        c.ConfigurableHTTPProxy.should_start = False

        # Setup binding of the hub's network interface, which points to the k8s
        # service for the hub.
        c.JupyterHub.base_url = "/n2"
        c.JupyterHub.hub_bind_url = "http://:8081"
        c.JupyterHub.hub_connect_url = "http://hub:8081"

        self.log.info("JupyterHub configuration complete")
        self.log.debug(f"JupyterHub configuration is now: {c}")
