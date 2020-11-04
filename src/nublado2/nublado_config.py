# """Configuration definition."""

__all__ = ["NubladoConfig"]

from typing import Any, Dict, Tuple

import yaml
from traitlets.config import LoggingConfigurable


class NubladoConfig(LoggingConfigurable):
    def get(self) -> Dict[str, Any]:
        with open("/etc/jupyterhub/nublado_config.yaml") as f:
            nc = yaml.load(f.read(), yaml.FullLoader)

        self.log.debug(f"Loaded Nublado Config:\n{nc}")
        return nc

    def lookup_size(self, name) -> Tuple[float, str]:
        sizes = self.get()["options_form"]["sizes"]

        for s in sizes:
            if s["name"] == name:
                return (float(s["cpu"]), s["ram"])

        raise ValueError(f"Size {name} not found")

    def lookup_image_url(self, name) -> str:
        images = self.get()["options_form"]["images"]

        for i in images:
            if i["name"] == name:
                return i["image"]

        raise ValueError(f"Image url for {name} not found")
