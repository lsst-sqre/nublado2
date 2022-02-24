# """Configuration definition."""

__all__ = ["HubConfig"]

import os

from aiohttp import BaseConnector, ClientSession
from jupyterhub.app import JupyterHub
from traitlets.config import LoggingConfigurable

from .hooks import NubladoHooks
from .nublado_config import NubladoConfig


class HubConfig(LoggingConfigurable):
    def configure(self, c: JupyterHub) -> None:
        self.log.info("Configuring JupyterHub Nublado2 style")
        self.log.debug(f"JupyterHub configuration starting as: {c}")

        nc = NubladoConfig()
        self.log.debug(f"Nublado Config is:\n{nc}")

        # This will possibly eventually move into upstream z2jh

        # Monkeypatch aiohttp connection noise (optional)
        #
        # There's a long and boring story about why, because the Reflector
        #  is a shared singleton across Spawners, we can't actually close it
        #  down cleanly, and if we want to use shared k8s API clients, we
        #  can't use them as properly self-closing context managers.
        #
        # If you don't do this patching, then you will have a bunch of
        #  errors in JupyterHub logs that don't tell you anything useful.
        #
        # Verify for yourself that we really are just patching out warnings:
        # https://github.com/aio-libs/aiohttp/blob/d01e257da9b37c35c68b3931026a2d918c271446/aiohttp/client.py#L295-L310  # noqa
        # https://github.com/aio-libs/aiohttp/blob/d01e257da9b37c35c68b3931026a2d918c271446/aiohttp/connector.py#L240-L258  # noqa

        def empty_fn(*args, **kwargs):
            pass

        def quiet_close(self, **kwargs):
            if self._closed:
                return
            if not self._conns:
                return
            if hasattr(self, "_close_immediately"):
                _ = self._close_immediately()

        ClientSession.__del__ = empty_fn
        BaseConnector.__del__ = quiet_close

        c.JupyterHub.hub_connect_url = self._get_hub_connect_url()
        # Turn off concurrent spawn limit
        c.JupyterHub.concurrent_spawn_limit = 0

        # Setup hooks
        hooks = NubladoHooks()
        c.Spawner.pre_spawn_hook = hooks.pre_spawn
        c.Spawner.post_stop_hook = hooks.post_stop
        c.Spawner.options_form = hooks.show_options
        c.Spawner.options_from_form = hooks.options_from_form
        # Turn off restart after n consecutive failures
        c.Spawner.consecutive_failure_limit = 0
        # Use JupyterLab by default
        c.Spawner.default_url = "/lab"

        c.KubeSpawner.enable_user_namespaces = True

        # This is how long the hub will wait for a lab pod to start.
        # For large images, this also includes the time it takes to
        # pull the docker image and start it.
        c.KubeSpawner.start_timeout = 10 * 60  # 10 minutes

        # This is how long to wait after the lab pod starts before
        # the hub will give up waiting for the lab to start.  When
        # using the debug flag, sometimes this can take longer than
        # the default, which is 30 seconds.
        c.KubeSpawner.http_timeout = 90

        # 'nb' will save us a little bit of horizontal space on the prompt
        # relative to 'jupyter'
        c.KubeSpawner.pod_name_template = "nb-{username}--{servername}"

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

        # Helm is pretty weird about not being able to merge dicts
        # together.  We use the extraVolumes and extraVolumeMounts
        # for the standard things we create.  We use this other section
        # to add more volumes without needing to copy the entire set
        # of volumes and mounts everywhere we use it.
        c.KubeSpawner.volumes.extend(nc.volumes)
        c.KubeSpawner.volume_mounts.extend(nc.volume_mounts)

        self.log.info("JupyterHub configuration complete")
        self.log.debug(f"JupyterHub configuration is now: {c}")

    def _get_hub_connect_url(self) -> str:
        ns_file = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"

        with open(ns_file) as f:
            namespace = f.read().strip()
            port = os.environ["HUB_SERVICE_PORT"]
            return f"http://hub.{namespace}:{port}"
