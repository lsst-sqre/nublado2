from jinja2 import Template
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
     id="{{ i.name }}" value="{{ i.name }}"
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


class NubladoOptions(LoggingConfigurable):
    def show_options_form(self, spawner) -> str:
        options_config = NubladoConfig().get()["options_form"]
        images = options_config["images"]
        sizes = options_config["sizes"]
        return options_template.render(images=images, sizes=sizes)
