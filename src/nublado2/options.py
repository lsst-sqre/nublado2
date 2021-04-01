from typing import Dict, List, Optional

from aiohttp import ClientSession
from jinja2 import Template
from jupyterhub.spawner import Spawner
from traitlets.config import LoggingConfigurable

from nublado2.imageinfo import ImageInfo, dropdown_fake_image
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
<!--
-->
{% for i in cached_images %}
    <input type="radio" name="image_list"
     id="{{ i.display_name }}" value="{{ i.packed_string }}"
     {% if loop.first %} checked {% endif %}
    >
    {{ i.name }}<br />
{% endfor %}

    <input type="radio" name="image_list"
        id="{{ dropdown_fake_image.display_name }}"
        value="dropdown_fake_image.packed_string">
    Select historical image:<br />
    <select name="image_dropdown">
    {% for i in all_images %}
        <option id="{{ i.display_name }}"
            value="{{ i.packed_string }}">{{ i.display_name }}</option>
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

        cachemachine_response = await self._get_images_from_url(images_url)

        all_imageinfos = []
        # Can't do this inside a comprehension (at least not without some
        #  godawful lambda thing) since ImageInfo() fills its fields
        #  separately rather than in the constructor
        for img in cachemachine_response["all"]:
            entry = ImageInfo()
            entry.from_cachemachine_entry(img)
            all_imageinfos.append(entry)
        # Start with the cachemachine response, then extend it with
        #  contents of options_config
        cached_images = cachemachine_response["images"]
        cached_images.extend(options_config["images"])
        cached_imageinfos = []
        for img in cached_images:
            entry = ImageInfo()
            entry.from_cachemachine_entry(img)
            cached_imageinfos.append(entry)
        fake_image = dropdown_fake_image()
        return options_template.render(
            dropdown_fake_image=fake_image,
            cached_images=cached_imageinfos,
            all_images=all_imageinfos,
            sizes=sizes,
        )

    async def _get_images_from_url(
        self, url: Optional[str]
    ) -> Dict[str, List[Dict[str, str]]]:
        if not url:
            return {"all": [], "images": []}

        r = await session.get(url)
        if r.status != 200:
            raise Exception(f"Error {r.status} from {url}")

        return await r.json()
