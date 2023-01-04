from dataclasses import dataclass
from typing import Any, Dict

import inflect

# See the K8s Python API's client.CustomObjectsApi() and
# create_namespaced_custom_object for examples.  The namespace field will
# be supplied at object creation time and therefore is not present in the
# CRDParser class

CRDBody = Dict[str, Any]
# This represents the body of a K8s custom object.

_p = inflect.engine()


@dataclass(frozen=True)
class CRDParser:
    group: str
    """Group is the K8s API group for the custom resource.
    e.g. 'ricoberger.de'"""

    version: str
    """Version is the API version.  e.g. 'v1alpha1'"""

    name: str
    """Name is the name of this CRD object.  e.g. 'butler-secret'"""

    plural: str
    """The plural of this object Kind.  We just defer to the 'inflect'
    package for this."""

    @classmethod
    def from_crd_body(cls, body: CRDBody) -> "CRDParser":
        """Ingest a Python Dict representation of a Custom Resource, and
        return a CRDParser with the properties filled out.  Raises KeyError
        if required fields are not present.  Required fields are currently:
        'apiVersion', 'kind', and 'metadata.name'.  The 'apiVersion' field
        must contain a slash, with the group before the slash and the version
        after it; raises IndexError if that isn't true."""
        (group, version) = body["apiVersion"].split("/")
        return cls(
            group=group,
            version=version,
            name=body["metadata"]["name"],
            plural=_p.plural(body["kind"].lower()),
        )
