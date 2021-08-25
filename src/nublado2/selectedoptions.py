from typing import Any, Dict

from nublado2.imageinfo import ImageInfo
from nublado2.labsize import LabSize
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
        if "image_list" in options:
            image = options["image_list"][0]
            if image == DROPDOWN_SENTINEL_VALUE:
                image = options["image_dropdown"][0]
        else:
            image = options["image_dropdown"][0]
        size_name = options["size"][0]

        self._image_info = ImageInfo.from_packed_string(image)

        nc = NubladoConfig()
        self._size = nc.sizes[size_name]

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
    def size(self) -> LabSize:
        return self._size
