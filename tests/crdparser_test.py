"""Tests for the ImageInfo class.
"""

import inflect

from nublado2.crdparser import CRDParser

_p = inflect.engine()

TEST_GROUP = "ricoberger.de"
TEST_VERSION = "v1alpha1"
TEST_KIND = "VaultSecret"
TEST_NAME = "butler-secret"

TEST_CRD_BODY = {
    "apiVersion": f"{TEST_GROUP}/{TEST_VERSION}",
    "kind": TEST_KIND,
    "metadata": {"name": TEST_NAME},
    "spec": {"path": "secret/k8s_operator/minikube.lsst.codes/butler-secret"},
}


def test_crdparser() -> None:
    """Create from a string we assemble."""
    crd = CRDParser.from_crd_body(TEST_CRD_BODY)
    assert crd.group == TEST_GROUP
    assert crd.version == TEST_VERSION
    assert crd.name == TEST_NAME
    assert crd.plural == _p.plural(TEST_KIND.lower())
