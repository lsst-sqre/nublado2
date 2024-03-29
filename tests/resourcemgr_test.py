"""Tests for the ResourceManager class."""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Dict, Iterator, List
from unittest.mock import Mock, patch

import pytest
from jupyterhub.user import User
from kubernetes_asyncio.client import (
    ApiClient,
    V1Container,
    V1EnvVar,
    V1ObjectMeta,
    V1Pod,
    V1PodSpec,
)
from kubespawner.spawner import KubeSpawner

from nublado2.crdparser import CRDParser
from nublado2.imageinfo import ImageInfo
from nublado2.nublado_config import NubladoConfig
from nublado2.resourcemgr import ResourceManager
from nublado2.selectedoptions import SelectedOptions

# Mock user resources template to test the template engine.
USER_RESOURCES_TEMPLATE = """
- apiVersion: v1
  kind: ConfigMap
  metadata:
    name: group
    namespace: "{{ user_namespace }}"
  data:
    user: |
      {{user}}:x:{{uid}}:{{gid if gid else uid}}::/home/{{ user }}:/bin/bash
    group: |
      {%- for group in groups %}{% if "id" in group %}
      {{ group.name }}:x:{{ group.id }}:\
{{ user if group.id != gid else ""}}{% endif %}{% endfor %}
- apiVersion: v1
  kind: ConfigMap
  metadata:
    name: dask
    namespace: "{{ user_namespace }}"
  data:
    dask_worker.yml: |
      {{ dask_yaml | indent(6) }}
- apiVersion: ricoberger.de/v1alpha1
  kind: VaultSecret
  metadata:
    name: butler-secret
    namespace: "{{ user_namespace }}"
  spec:
    path: "{{ butler_secret_path }}"
    type: Opaque
"""


class KubernetesApiMock:
    """Mocks the bits of the Kubernetes API that we use.

    This simulates both the CoreV1Api and the CustomObjectsApi (but only
    portions of each).
    """

    def __init__(self) -> None:
        self.objects: List[Dict[str, Any]] = []
        self.custom: List[Dict[str, Any]] = []
        self.api_client = ApiClient()

    async def create_object(self, kind: str, body: Any) -> bool:
        body_as_dict = self.api_client.sanitize_for_serialization(body)
        self.objects.append(body_as_dict)
        return True

    async def create_namespaced_custom_object(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        body: Dict[str, Any],
    ) -> None:
        crd_info = CRDParser.from_crd_body(body)
        assert crd_info.group == group
        assert crd_info.version == version
        assert crd_info.plural == plural
        assert body["metadata"]["namespace"] == namespace
        self.custom.append(body)

    def shared_client_mock(self, typ: str) -> Any:
        return self.api_client if typ == "ApiClient" else self


@pytest.fixture(autouse=True)
def config_mock() -> Iterator[None]:
    with patch("nublado2.resourcemgr.NubladoConfig") as mock:
        mock.return_value = Mock(spec=NubladoConfig)
        mock.return_value.base_url = "https://data.example.com/"
        mock.return_value.gafaelfawr_token = "admin-token"
        mock.return_value.butler_secret_path = "k8s_operator/data/butler"
        mock.return_value.user_resources_template = USER_RESOURCES_TEMPLATE
        mock.return_value.lab_environment = {
            "EXTERNAL_INSTANCE_URL": "{{ base_url }}",
            "FIREFLY_ROUTE": "/portal/app",
            "HUB_ROUTE": "{{ nublado_base_url }}",
            "EXTERNAL_GROUPS": "{{ external_groups }}",
            "EXTERNAL_GID": "{{ gid }}",
            "EXTERNAL_UID": "{{ uid }}",
            "ACCESS_TOKEN": "{{ token }}",
            "IMAGE_DIGEST": "{{ options.image_info.digest }}",
            "IMAGE_DESCRIPTION": "{{ options.image_info.display_name }}",
            "CLEAR_DOTLOCAL": "{{ options.clear_dotlocal }}",
            "DEBUG": "{{ options.debug }}",
        }
        with patch("nublado2.provisioner.NubladoConfig") as provisioner_mock:
            provisioner_mock.return_value = mock.return_value
            yield


@pytest.fixture(autouse=True)
def kubernetes_api_mock() -> Iterator[KubernetesApiMock]:
    mock_api = KubernetesApiMock()
    with patch("nublado2.resourcemgr.create_from_dict") as create_mock:
        create_mock.side_effect = lambda _, r: mock_api.objects.append(r)
        with patch("nublado2.resourcemgr.shared_client") as client_mock:
            client_mock.side_effect = mock_api.shared_client_mock
            yield mock_api


@pytest.mark.asyncio
async def test_create_kubernetes_resources(
    kubernetes_api_mock: KubernetesApiMock,
) -> None:
    spawner = Mock(spec=KubeSpawner)
    spawner.k8s_api_request_timeout = 3
    spawner.k8s_api_request_retry_timeout = 30
    spawner.namespace = "nublado2-someuser"
    spawner.extra_annotations = {
        "argocd.argoproj.io/compare-options": "IgnoreExtraneous",
        "argocd.argoproj.io/sync-options": "Prune=false",
    }
    spawner.extra_labels = {
        "hub.jupyter.org/network-access-hub": "true",
        "argocd.argoproj.io/instance": "nublado-users",
    }
    spawner._make_create_resource_request = kubernetes_api_mock.create_object
    spawner.hub = Mock()
    spawner.hub.base_url = "/nb/hub/"
    spawner.user = Mock(spec=User)
    spawner.user.name = "someuser"
    spawner.api = kubernetes_api_mock
    auth_state = {
        "token": "user-token",
        "uid": 1234,
        "gid": 1551,
        "groups": [
            {"name": "foo", "id": 1235},
            {"name": "primary", "id": 1551},
            {"name": "bar", "id": 4567},
            {"name": "baz"},
        ],
    }
    pod_manifest = V1Pod(
        api_version="v1",
        kind="Pod",
        metadata=V1ObjectMeta(
            name="user-pod",
            namespace=spawner.namespace,
        ),
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name="container",
                    command=["run-something"],
                    env=[V1EnvVar(name="FOO", value="BAR")],
                    image="blah:latest",
                )
            ],
        ),
    )
    if sys.version_info < (3, 8):
        spawner.get_pod_manifest.return_value = asyncio.Future()
        spawner.get_pod_manifest.return_value.set_result(pod_manifest)
        spawner.user.get_auth_state.return_value = asyncio.Future()
        spawner.user.get_auth_state.return_value.set_result(auth_state)
    else:
        spawner.get_pod_manifest.return_value = pod_manifest
        spawner.user.get_auth_state.return_value = auth_state

    options = Mock(spec=SelectedOptions)
    options.debug = "true"
    options.clear_dotlocal = "true"
    options.image_info = ImageInfo(
        reference="registry.hub.docker.com/lsstsqre/sciplat-lab:w_2021_13",
        display_name="blah blah blah",
        digest="sha256:123456789abcdef",
    )

    resource_manager = ResourceManager()
    await resource_manager._create_kubernetes_resources(spawner, options)

    assert sorted(
        kubernetes_api_mock.objects,
        key=lambda o: (o["kind"], o["metadata"]["name"]),
    ) == [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "dask",
                "namespace": spawner.namespace,
                "annotations": spawner.extra_annotations,
                "labels": spawner.extra_labels,
            },
            "data": {
                "dask_worker.yml": f"""\
apiVersion: v1
kind: Pod
metadata:
  namespace: {spawner.namespace}
spec:
  containers:
    - command:
        - run-something
      env:
        - name: FOO
          value: BAR
        - name: DASK_WORKER
          value: 'TRUE'
      image: blah:latest
      name: container
"""
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "group",
                "namespace": spawner.namespace,
                "annotations": spawner.extra_annotations,
                "labels": spawner.extra_labels,
            },
            "data": {
                "user": "someuser:x:1234:1551::/home/someuser:/bin/bash\n",
                "group": (
                    "foo:x:1235:someuser\n"
                    "primary:x:1551:\n"
                    "bar:x:4567:someuser\n"
                ),
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "lab-environment",
                "namespace": spawner.namespace,
                "annotations": spawner.extra_annotations,
                "labels": spawner.extra_labels,
            },
            "data": {
                "EXTERNAL_INSTANCE_URL": "https://data.example.com/",
                "FIREFLY_ROUTE": "/portal/app",
                "HUB_ROUTE": "/nb/hub/",
                "EXTERNAL_GID": "1551",
                "EXTERNAL_GROUPS": "foo:1235,primary:1551,bar:4567",
                "EXTERNAL_UID": "1234",
                "ACCESS_TOKEN": "user-token",
                "IMAGE_DIGEST": "sha256:123456789abcdef",
                "IMAGE_DESCRIPTION": "blah blah blah",
                "CLEAR_DOTLOCAL": "true",
                "DEBUG": "true",
            },
        },
    ]

    assert sorted(
        kubernetes_api_mock.custom,
        key=lambda o: (o["kind"], o["metadata"]["name"]),
    ) == [
        {
            "apiVersion": "ricoberger.de/v1alpha1",
            "kind": "VaultSecret",
            "metadata": {
                "name": "butler-secret",
                "namespace": spawner.namespace,
                "annotations": spawner.extra_annotations,
                "labels": spawner.extra_labels,
            },
            "spec": {
                "path": "k8s_operator/data/butler",
                "type": "Opaque",
            },
        }
    ]
