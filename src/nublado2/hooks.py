from typing import Any, Dict

from jupyterhub.spawner import Spawner
from traitlets.config import LoggingConfigurable

from nublado2.nublado_config import NubladoConfig
from nublado2.options import NubladoOptions
from nublado2.resourcemgr import ResourceManager


class NubladoHooks(LoggingConfigurable):
    def __init__(self) -> None:
        self.resourcemgr = ResourceManager()
        self.optionsform = NubladoOptions()

    async def pre_spawn(self, spawner: Spawner) -> None:
        user = spawner.user.name
        options = spawner.user_options
        self.log.debug(
            f"Pre-spawn hook called for {user} with options {options}"
        )

        # Look up what the user selected on the options form.
        # Each parameter comes back as a list, even if only one is
        # selected.
        size_name = options["size"][0]
        image_info = options["image_info"][0]
        image_name = image_info.split("|")[0]
        image_tag = options["image_tag"][0]

        # If the user selected one of the images in the dropdown,
        # use image.
        if image_name == "image_tag":
            image_name = image_tag

        # Take size and image names, which are returned as form data,
        # look up associated values, and configure the spawner.
        # This will help set up the created lab pod.
        nc = NubladoConfig()
        (cpu, ram) = nc.lookup_size(size_name)
        spawner.image = image_name
        spawner.debug = options.get("debug_enabled", False)
        spawner.mem_limit = ram
        spawner.cpu_limit = cpu

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

        await self.resourcemgr.create_user_resources(spawner)

    def post_stop(self, spawner: Spawner) -> None:
        user = spawner.user.name
        self.log.debug(f"Post stop-hook called for {user}")
        self.resourcemgr.delete_user_resources(spawner.namespace)

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
