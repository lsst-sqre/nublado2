from typing import Dict, List, Optional

from aiohttp import ClientSession
from jinja2 import Template
from jupyterhub.spawner import Spawner
from traitlets.config import LoggingConfigurable

from nublado2.nublado_config import NubladoConfig

options_template = Template(
    """
<style>
    td {
        border: 1px solid black;
        padding: 2%;
        vertical-align: top;
    }
</style>

<table width="100%">
<tr>
  <th>Image</th>
  <th>Options</th>
</tr>

<tr>

<td width="50%">
{% for i in images %}
    <input type="radio" name="image"
     id="{{ i.name }}" value="{{ i.image_url }}"
     {% if loop.first %} checked {% endif %}
    >
    {{ i.name }}<br />
{% endfor %}
</td>

<td width="50%">
{% for s in sizes %}
    <input type="radio" name="size"
     id="{{ s.name }}" value="{{ s.name }}"
     {% if loop.first %} checked {% endif %}
    >
    {{ s.name }} ({{ s.cpu }} CPU, {{ s.ram }} RAM)<br>
{% endfor %}

    <br>
    <input type="checkbox"
     name="enable_debug" value="true">Enable debug logs<br>
</td>

</tr>
</table>
"""
)

# Don't have this be a member of NubladoOptions, we should
# share this connection pool.  Also the LoggingConfigurable
# will try to pickle it to json, and it can't pickle a session.
session = ClientSession()


class NubladoOptions(LoggingConfigurable):
    async def show_options_form(self, spawner: Spawner) -> str:
        options_config = NubladoConfig().get()["options_form"]
        sizes = options_config["sizes"]

        images_url = options_config.get("images_url")
        images = await self._get_images_from_url(images_url)
        images.extend(options_config["images"])

        return options_template.render(images=images, sizes=sizes)

    async def _get_images_from_url(
        self, url: Optional[str]
    ) -> List[Dict[str, str]]:
        if not url:
            return []

        r = await session.get(url)
        if r.status != 200:
            raise Exception(f"Error {r.status} from {url}")

        return await r.json()
