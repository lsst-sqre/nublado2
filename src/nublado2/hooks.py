# from jupyterhub.spawner import Spawner

from jupyterhub.spawner import Spawner
from traitlets.config import LoggingConfigurable


class NubladoHooks(LoggingConfigurable):
    def pre_spawn(self, spawner: Spawner) -> None:
        self.log.debug(f"Pre-spawn hook called for {spawner.user.name}")
