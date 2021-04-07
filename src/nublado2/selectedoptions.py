from typing import Any, Dict

from nublado2.imageinfo import ImageInfo
from nublado2.nublado_config import NubladoConfig
from nublado2.options import DROPDOWN_SENTINEL_VALUE


class SelectedOptions:
    """This class parses the returned options form into fields.

    Use this code to add additional options to the spawner form that
    get parsed out of the user return form data.  That way we can
    have strong typing over them, and one place to parse them out."""

    def __init__(self, options: Dict[str, Any]) -> None:
        """Create a SelectedOptions instance from the formdata."""

        # Each parameter comes back as a list, even if only one is
        # selected.
        image_list = options["image_list"][0]
        image_dropdown = options["image_dropdown"][0]
        size_name = options["size"][0]

        if image_list == DROPDOWN_SENTINEL_VALUE:
            self._image_info = ImageInfo.from_packed_string(image_dropdown)
        else:
            self._image_info = ImageInfo.from_packed_string(image_list)

        nc = NubladoConfig()
        (self._cpu, self._ram) = nc.lookup_size(size_name)

        self._debug = "TRUE" if "enable_debug" in options else ""
        self._clear_dotlocal = "TRUE" if "clear_dotlocal" in options else ""

    @property
    def debug(self) -> str:
        """String to pass in for the DEBUG environment variable in the lab

        This sets up the nublado lab containers to emit more debug info,
        but doesn't work the same way the kubespawner.debug attribute does."""
        return self._debug

    @property
    def clear_dotlocal(self) -> str:
        """String to pass in for CLEAR_DOTLOCAL variable in the lab.

        This gets rid of the user's .local directory which may
        cause issues during startup."""
        return self._clear_dotlocal

    @property
    def image_info(self) -> ImageInfo:
        """Information on the Docker image to run for the lab."""
        return self._image_info

    @property
    def cpu(self) -> float:
        """Number of vCPUs for the lab pod.  Comes from the size."""
        return self._cpu

    @property
    def ram(self) -> str:
        """Amount of RAM for the lab pod.

        This is in kubernetes format, like 2g or 2048M, and comes
        from the size."""
        return self._ram
