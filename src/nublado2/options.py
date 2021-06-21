from typing import List, Optional, Tuple

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
    document.forms['spawn_form'].image_list.value = '{{ dropdown_sentinel }}';
}
</script>

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
<!--
-->
{% for i in cached_images %}
    <input type="radio" name="image_list"
     id="{{ i.display_name }}" value="{{ i.packed_string }}"
     {% if loop.first %} checked {% endif %}
    >
    {{ i.display_name }}<br />
{% endfor %}

    <input type="radio" name="image_list"
        id="{{ dropdown_sentinel }}"
        value="{{ dropdown_sentinel }}">
    Select uncached image (slower start):<br />
    <select name="image_dropdown" onchange="selectDropdown()">
    {% for i in all_images %}
        <option value="{{ i.packed_string }}">{{ i.display_name }}</option>
    {% endfor %}
    </select>
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
     name="enable_debug" value="true">
        Enable debug logs<br>
    <input type="checkbox"
     name="clear_dotlocal" value="true">
        Clear <tt>.local</tt> directory (caution!)<br>
</td>

</tr>
</table>
"""
)


class NubladoOptions(LoggingConfigurable):
    async def show_options_form(self, spawner: Spawner) -> str:
        nc = NubladoConfig()

        (cached_images, all_images) = await self._get_images_from_url(
            nc.images_url
        )
        cached_images.extend(nc.pinned_images)

        return options_template.render(
            dropdown_sentinel=DROPDOWN_SENTINEL_VALUE,
            cached_images=cached_images,
            all_images=all_images,
            sizes=nc.sizes.values(),
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
