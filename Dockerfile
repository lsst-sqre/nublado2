FROM jupyterhub/jupyterhub:1.2

# Update system packages
COPY scripts/install-base-packages.sh .
RUN ./install-base-packages.sh

COPY . /nublado2
WORKDIR /nublado2

# Install the app's Python runtime dependencies, then the app.
RUN pip install --quiet --no-cache-dir -r /nublado2/requirements/main.txt
RUN pip install --no-cache-dir .

# Create a non-root user to run the Hub.
RUN useradd --create-home jovyan
WORKDIR /home/jovyan

USER jovyan
ENTRYPOINT ["jupyterhub", "--config", "/nublado2/jupyterhub_config.py"]
