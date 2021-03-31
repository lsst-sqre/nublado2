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
<!-- The values returned from the form are in the form of a pipe-separated
string.  The first value is the Docker specification of the image.  The
second value is the human-friendly description of the image.  The third value
is the hash, if known (if not, the following string will be zero-length).

If the dropdown for historical images is used, the value in the image_info
radio button will be "image_from_dropdown||" and the class into which
these results are received will know to use, rather than ignore, the value
coming from the image_dropdown field instead.

That field will be in the same form, with the same values, although the
description is slightly less human friendly.
-->
{% for i in images %}
    <input type="radio" name="image_list"
     id="{{ i.name }}" value="{{ i.image_url }}|{{ i.name}}|{{ i.image_hash }}"
     {% if loop.first %} checked {% endif %}
    >
    {{ i.name }}<br />
{% endfor %}

    <input type="radio" name="image_list" id="image_from_dropdown"
        value="image_from_dropdown||">
    Select historical image:<br />
    <select name="image_dropdown">
    {% for i in all_images %}
        <option value="{{ i.image_url }}|{{ i.name }}|">{{ i.name }}</option>
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

        all_images = cachemachine_response["all"]
        images = cachemachine_response["images"]
        images.extend(options_config["images"])
        return options_template.render(
            all_images=all_images, images=images, sizes=sizes
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
