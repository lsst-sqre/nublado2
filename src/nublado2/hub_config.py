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

        nc = NubladoConfig()
        self.log.debug(f"Nublado Config is:\n{nc}")

        c.JupyterHub.hub_connect_url = self._get_hub_connect_url()

        # Setup hooks
        hooks = NubladoHooks()
        c.Spawner.pre_spawn_hook = hooks.pre_spawn
        c.Spawner.post_stop_hook = hooks.post_stop
        c.Spawner.options_form = hooks.show_options
        c.Spawner.options_from_form = hooks.options_from_form

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
