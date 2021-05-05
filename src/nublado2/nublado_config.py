# """Configuration definition."""

__all__ = ["NubladoConfig"]

from typing import Any, Dict, List, Optional

from ruamel import yaml
from ruamel.yaml import RoundTripLoader

from nublado2.imageinfo import ImageInfo
from nublado2.labsize import LabSize


class NubladoConfig:
    def __init__(self) -> None:
        """Load the nublado_config.yaml file from disk.

        This file normally comes from mounting a configmap with the
        nublado_config.yaml mounted into the hub container."""
        with open("/etc/jupyterhub/nublado_config.yaml") as f:
            self._config = yaml.load(f.read(), Loader=RoundTripLoader)

        self._sizes = {
            s.name: s
            for s in [
                LabSize(float(s["cpu"]), s["name"], s["ram"])
                for s in self._config["sizes"]
            ]
        }

    @property
    def base_url(self) -> str:
        """Base URL for the environment, like https://data.lsst.cloud"""
        return self._config["base_url"]

    @property
    def gafaelfawr_token(self) -> Optional[str]:
        """Retrieve the Gafaelfawr token for moneypenny calls."""
        try:
            with open("/etc/keys/gafaelfawr-token") as f:
                return f.read()
        except FileNotFoundError:
            return None

    @property
    def images_url(self) -> str:
        """URL to fetch list of images to show in options form.

        Generally, this is a link to the cachemachine service."""
        return self._config["images_url"]

    @property
    def lab_environment(self) -> Dict[str, str]:
        """Environment variable settings for the lab (possibly templates)."""
        return dict(self._config.get("lab_environment", {}))

    @property
    def pinned_images(self) -> List[ImageInfo]:
        """List of images to keep pinned in the options form."""
        return [
            ImageInfo.from_cachemachine_entry(i)
            for i in self._config["pinned_images"]
        ]

    @property
    def signing_key(self) -> str:
        """Retrieve the gafaelfawr signing key to mint tokens."""
        with open("/etc/keys/signing_key.pem", "r") as f:
            return f.read()

    @property
    def sizes(self) -> Dict[str, LabSize]:
        """Retrieve a copy of the sizes a lab can spawn as."""
        return dict(self._sizes)

    @property
    def user_resources_template(self) -> str:
        """Retrieve a copy of the lab resources templates."""
        return self._config.get("user_resources_template")

    @property
    def volumes(self) -> List[Dict[str, Any]]:
        return list(self._config["volumes"])

    @property
    def volume_mounts(self) -> List[Dict[str, Any]]:
        return list(self._config["volume_mounts"])

    @property
    def butler_secret_path(self) -> str:
        return self._config.get("butler_secret_path")
