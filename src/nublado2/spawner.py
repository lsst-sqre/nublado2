from kubespawner import KubeSpawner


class NubladoSpawner(KubeSpawner):
    """
    A subclass of KubeSpawner so we can interpret the options form data
    returned to us.  Sadly this functionality isn't available as a hook,
    so it must be subclassed.
    """

    def options_from_form(self, formdata):
        """
        This gets the options returned from the options form.
        This returned data is passed to the pre_spawn_hook as the options
        argument.
        """
        self.log.debug(
            f"Options_from_form for {self.user.name} with data {formdata}"
        )
        return formdata
