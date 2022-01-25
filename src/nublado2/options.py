"""Spawner option form handling."""

from __future__ import annotations

from typing import List, Optional, Tuple
from urllib.parse import urljoin

from jinja2 import Template
from jupyterhub.spawner import Spawner
from traitlets.config import LoggingConfigurable

from nublado2.http import get_session
from nublado2.imageinfo import ImageInfo
from nublado2.nublado_config import NubladoConfig

DROPDOWN_SENTINEL_VALUE = "use_image_from_dropdown"

options_template = Template(
    """

<script>
function selectDropdown() {
    document.getElementById('{{ dropdown_sentinel }}').checked = true;
}
</script>

<style>
    td {
        border: 1px solid black;
        padding: 2%;
        vertical-align: top;
    }
    .radio label,
    .checkbox label {
        padding-left: 0px;
    }
</style>

<table width="100%">
<tr>
  <th>Image</th>
  <th>Options</th>
</tr>

<tr>

<td width="50%">
  <div class="radio radio-inline">
{% for i in cached_images %}
    <input type="radio" name="image_list"
     id="image{{ loop.index }}" value="{{ i.packed_string }}"
     {% if loop.first %} checked {% endif %}
    >
    <label for="image{{ loop.index }}">{{ i.display_name }}</label><br />
{% endfor %}

    <input type="radio" name="image_list"
        id="{{ dropdown_sentinel }}"
        value="{{ dropdown_sentinel }}"
        {% if not cached_images %} checked {% endif %}
    >
    <label for="{{ dropdown_sentinel }}">
      Select uncached image (slower start):
    </label><br />
    <select name="image_dropdown" onclick="selectDropdown()">
    {% for i in all_images %}
        <option value="{{ i.packed_string }}">{{ i.display_name }}</option>
    {% endfor %}
    </select>
  </div>
</td>

<td width="50%">
  <div class="radio radio-inline">
{% for s in sizes %}
    <input type="radio" name="size"
     id="{{ s.name }}" value="{{ s.name }}"
     {% if loop.first %} checked {% endif %}
    >
    <label for="{{ s.name }}">
      {{ s.name }} ({{ s.cpu }} CPU, {{ s.ram }} RAM)
    </label><br />
{% endfor %}
  </div>

  <br />
  <br />
  <div class="checkbox checkbox-inline">
    <input type="checkbox" id="enable_debug"
     name="enable_debug" value="true">
    <label for="enable_debug">Enable debug logs</label><br />

    <input type="checkbox" id="clear_dotlocal"
     name="clear_dotlocal" value="true">
    <label for="clear_dotlocal">
      Clear <tt>.local</tt> directory (caution!)
    </label><br />
  </div>
</td>

</tr>
</table>
"""
)


class NubladoOptions(LoggingConfigurable):
    def __init__(self) -> None:
        self.nublado_config = NubladoConfig()

    async def show_options_form(self, spawner: Spawner) -> str:
        base_url = self.nublado_config.base_url
        url = urljoin(base_url, "cachemachine/jupyter/available")
        (cached_images, all_images) = await self._get_images_from_url(url)
        cached_images.extend(self.nublado_config.pinned_images)

        return options_template.render(
            dropdown_sentinel=DROPDOWN_SENTINEL_VALUE,
            cached_images=cached_images,
            all_images=all_images,
            sizes=self.nublado_config.sizes.values(),
        )

    async def _get_images_from_url(
        self, url: Optional[str]
    ) -> Tuple[List[ImageInfo], List[ImageInfo]]:
        if not url:
            return ([], [])

        session = await get_session()
        r = await session.get(url)
        if r.status != 200:
            raise Exception(f"Error {r.status} from {url}")

        body = await r.json()

        cached_images = [
            ImageInfo.from_cachemachine_entry(img) for img in body["images"]
        ]

        all_images = [
            ImageInfo.from_cachemachine_entry(img) for img in body["all"]
        ]

        return (cached_images, all_images)
