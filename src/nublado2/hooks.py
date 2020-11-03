from jupyterhub.spawner import Spawner
from traitlets.config import LoggingConfigurable

from nublado2.options import NubladoOptions
from nublado2.resourcemgr import ResourceManager


class NubladoHooks(LoggingConfigurable):
    def __init__(self) -> None:
        self.resourcemgr = ResourceManager()
        self.optionsform = NubladoOptions()

    def pre_spawn(self, spawner: Spawner) -> None:
        user = spawner.user.name
        options = spawner.user_options
        self.log.debug(
            f"Pre-spawn hook called for {user} with options {options}"
        )
        self.resourcemgr.create_user_resources(user)

    def post_stop(self, spawner: Spawner) -> None:
        user = spawner.user.name
        self.log.debug(f"Post stop-hook called for {user}")
        self.resourcemgr.delete_user_resources(user)

    def show_options(self, spawner: Spawner) -> str:
        user = spawner.user.name
        self.log.debug(f"Show options hook called for {user}")
        return self.optionsform.show_options_form(spawner)
