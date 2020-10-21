# """Configuration definition."""

__all__ = ["NubladoConfig"]

from typing import Any, Dict

import yaml
from traitlets.config import LoggingConfigurable


class NubladoConfig(LoggingConfigurable):
    def get(self) -> Dict[str, Any]:
        with open("/etc/jupyterhub/nublado_config.yaml") as f:
            nc = yaml.load(f.read(), yaml.FullLoader)

        self.log.debug(f"Loaded Nublado Config:\n{nc}")
        return nc
