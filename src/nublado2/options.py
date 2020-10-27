from traitlets.config import LoggingConfigurable


class NubladoOptions(LoggingConfigurable):
    def show_options_form(self, spawner) -> str:
        return """
<div class="form-group">
    <input type="radio" id="image-ver-1" name="image" value="image-ver-1">
    <label for="image-ver-1">Version 1</label><br>
    <input type="radio" id="image-ver-2" name="image" value="image-ver-2">
    <label for="image-ver-2">Version 2</label><br>
</div>
        """
