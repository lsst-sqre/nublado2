"""Configuration definition."""

__all__ = ["Configuration"]

import logging
import os
from dataclasses import dataclass

from jupyterhub.app import JupyterHub


def setup_config(c: JupyterHub) -> None:
    logging.info("Configuring JupyterHub Nublado2 style")
    c.JupyterHub.authenticator_class = "tmpauthenticator.TmpAuthenticator"
    c.JupyterHub.spawner_class = "kubespawner.KubeSpawner"

    # Point to the proxy pod, which is a k8s service for the proxy.
    c.ConfigurableHTTPProxy.api_url = "http://proxy-api:8001"
    c.ConfigurableHTTPProxy.should_start = False

    # Setup binding of the hub's network interface, which points to the k8s
    # service for the hub.
    c.JupyterHub.hub_bind_url = "http://:8081"
    c.JupyterHub.hub_connect_url = "http://hub:8081"


@dataclass
class Configuration:
    """Configuration for nublado2."""

    name: str = os.getenv("SAFIR_NAME", "nublado2")
    """The application's name, which doubles as the root HTTP endpoint path.

    Set with the ``SAFIR_NAME`` environment variable.
    """

    profile: str = os.getenv("SAFIR_PROFILE", "development")
    """Application run profile: "development" or "production".

    Set with the ``SAFIR_PROFILE`` environment variable.
    """

    logger_name: str = os.getenv("SAFIR_LOGGER", "nublado2")
    """The root name of the application's logger.

    Set with the ``SAFIR_LOGGER`` environment variable.
    """

    log_level: str = os.getenv("SAFIR_LOG_LEVEL", "INFO")
    """The log level of the application's logger.

    Set with the ``SAFIR_LOG_LEVEL`` environment variable.
    """
