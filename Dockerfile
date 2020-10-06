FROM jupyterhub/jupyterhub:1.2 as base-image

# Update system packages
COPY scripts/install-base-packages.sh .
RUN ./install-base-packages.sh

FROM base-image as dependencies-image

# Install the app's Python runtime dependencies
COPY requirements/main.txt ./requirements.txt
RUN pip install --quiet --no-cache-dir -r requirements.txt

FROM dependencies-image as runtime-image

# Install the nublado2 python module
COPY . /nublado2
WORKDIR /nublado2
RUN pip install --no-cache-dir .

# Place the config in the default location
COPY jupyterhub_config.py /etc/jupyterhub/jupyterhub_config.py

# Create a non-root user to run the Hub
RUN useradd --create-home jovyan
WORKDIR /home/jovyan

USER jovyan
EXPOSE 8000
EXPOSE 8081
ENTRYPOINT ["jupyterhub", "--config", "/etc/jupyterhub/jupyterhub_config.py"]
