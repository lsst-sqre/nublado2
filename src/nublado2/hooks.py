from typing import Any, Dict

from jupyterhub.spawner import Spawner
from traitlets.config import LoggingConfigurable

from nublado2.options import NubladoOptions
from nublado2.resourcemgr import ResourceManager
from nublado2.selectedoptions import SelectedOptions


class NubladoHooks(LoggingConfigurable):
    def __init__(self) -> None:
        self.resourcemgr = ResourceManager()
        self.optionsform = NubladoOptions()

    async def pre_spawn(self, spawner: Spawner) -> None:
        options = SelectedOptions(spawner.user_options)
        self.log.debug(
            f"Pre-spawn called for {spawner.user.name} with options {options}"
        )

        spawner.image = options.image_info.reference
        spawner.mem_limit = options.size.ram
        spawner.cpu_limit = options.size.cpu

        auth_state = await spawner.user.get_auth_state()

        # We now always spawn as the target user; there is no way
        #  to do "provisionator" anymore
        spawner.uid = auth_state["uid"]
        spawner.gid = auth_state["uid"]
        spawner.supplemental_gids = [g["id"] for g in auth_state["groups"]]

        # Since we will create a serviceaccount in the user resources,
        # make the pod use that.  This will also automount the token,
        # which is useful for dask.
        spawner.service_account = f"{spawner.user.name}-serviceaccount"

        await self.resourcemgr.create_user_resources(spawner, options)

    async def post_stop(self, spawner: Spawner) -> None:
        user = spawner.user.name
        self.log.debug(f"Post stop-hook called for {user}")
        await self.resourcemgr.delete_user_resources(
            spawner, spawner.namespace
        )

    async def show_options(self, spawner: Spawner) -> str:
        user = spawner.user.name
        self.log.debug(f"Show options hook called for {user}")
        return await self.optionsform.show_options_form(spawner)

    def options_from_form(self, formdata: Dict[str, Any]) -> Dict[str, Any]:
        """
        This gets the options returned from the options form.
        This returned data is passed to the pre_spawn_hook as the options
        argument.
        """
        self.log.debug(f"Options_from_form with data {formdata}")
        return formdata
