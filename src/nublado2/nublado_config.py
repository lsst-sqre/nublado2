# """Configuration definition."""

__all__ = ["NubladoConfig"]

from typing import Any, Dict, Optional, Tuple

from ruamel import yaml
from ruamel.yaml import RoundTripLoader
from traitlets.config import LoggingConfigurable


class NubladoConfig(LoggingConfigurable):
    def get(self) -> Dict[str, Any]:
        with open("/etc/jupyterhub/nublado_config.yaml") as f:
            nc = yaml.load(f.read(), Loader=RoundTripLoader)

        self.log.debug(f"Loaded Nublado Config:\n{nc}")
        return nc

    def lookup_size(self, name: str) -> Tuple[float, str]:
        sizes = self.get()["options_form"]["sizes"]

        for s in sizes:
            if s["name"] == name:
                return (float(s["cpu"]), s["ram"])

        raise ValueError(f"Size {name} not found")

    def pod_uid(self) -> Optional[int]:
        return self.get().get("pod_uid", None)

    def pod_cmd(self) -> Optional[str]:
        return self.get().get("pod_cmd", None)
