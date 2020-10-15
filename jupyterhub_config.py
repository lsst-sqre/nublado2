import nublado2.config

# This is the jupyterhub_config.py file.
# This is a little tricky, so try to keep this as short as possible.
#
# When JupyterHub loads, it will execute this python file, and the
# context of this execution has a variable c which is to be populated
# with the options that JupyterHub should use to start.
#
# For a listing of the various options and what they mean, please
# refer to:
# https://jupyterhub.readthedocs.io/en/stable/getting-started/config-basics.html
# The technical reference also provides a lot of examples on how
# to configure JupyterHub in various ways:
# https://jupyterhub.readthedocs.io/en/stable/reference/index.html
nublado2.config.setup_config(c)  # noqa: F821
