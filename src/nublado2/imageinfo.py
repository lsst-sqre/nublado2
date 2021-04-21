from dataclasses import dataclass
from typing import Dict

FIELD_DELIMITER = "|"

# This type is the dict that comes from cachemachine:
#  https: //github.com/lsst-sqre/cachemachine/blob/4802ab7d78aec27b400f66b9af3324180910476e/src/cachemachine/types.py#L50-L69  # noqa: E501
CachemachineEntry = Dict[str, str]


@dataclass(frozen=True)
class ImageInfo:
    reference: str
    """reference is a docker image reference.
    See:
     https://github.com/distribution/distribution/blob/main/reference/reference.go  # noqa: E501

    Example: "registry.hub.docker.com/lsstsqre/sciplat-lab:w_2021_13"
    """

    display_name: str
    """display_name is a human-readable description of the image.

    Example: "Weekly 13"
    """

    digest: str
    """digest is the hash of the last layer of the docker container.  If
    unknown, it will be the empty string.

    Example: "sha256:419c4b7e14603711b25fa9e0569460a753c4b2449fe275bb5f89743b01794a30"  # noqa: E501
    """

    @property
    def packed_string(self) -> str:
        """packed_string is the form in which the image info is packed into the
        JupyterHub options form and in which is is returned as the form
        selection.  It is specification, display_name, and digest
        concatenated with the pipe character.

        Example: "registry.hub.docker.com/lsstsqre/sciplat-lab:w_2021_13|Weekly 13|sha256:419c4b7e14603711b25fa9e0569460a753c4b2449fe275bb5f89743b01794a30"  # noqa: E501
        """
        return FIELD_DELIMITER.join(
            [self.reference, self.display_name, self.digest]
        )

    @classmethod
    def from_cachemachine_entry(cls, entry: CachemachineEntry) -> "ImageInfo":
        """Take an entry from a cachemachine response, and set our fields
        from it.
        """
        # entry uses None, we use empty string for missing digest
        return cls(
            reference=entry["image_url"],
            display_name=entry["name"],
            digest=entry.get("image_hash", ""),
        )

    @classmethod
    def from_packed_string(cls, packed_string: str) -> "ImageInfo":
        """Take an entry from an ImageInfo packed_string, and set our fields
        from it.
        """
        fields = packed_string.split(FIELD_DELIMITER)
        if len(fields) != 3:
            raise RuntimeError(
                f"Argument packed_string='{packed_string}'"
                + f" must have 3 {FIELD_DELIMITER}-separated"
                + " fields"
            )
        return cls(
            reference=fields[0], display_name=fields[1], digest=fields[2]
        )
