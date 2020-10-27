from jupyterhub.spawner import Spawner
from traitlets.config import LoggingConfigurable

from nublado2.resourcemgr import ResourceManager


class NubladoHooks(LoggingConfigurable):
    def __init__(self) -> None:
        self.resourcemgr = ResourceManager()

    def pre_spawn(self, spawner: Spawner) -> None:
        user = spawner.user.name
        self.log.debug(f"Pre-spawn hook called for {user}")
        self.resourcemgr.create_user_resources(user)

    def post_stop(self, spawner: Spawner) -> None:
        user = spawner.user.name
        self.log.debug(f"Post stop-hook called for {user}")
        self.resourcemgr.delete_user_resources(user)
