from dataclasses import dataclass, field
from typing import Dict

FIELD_DELIMITER = "|"
DROPDOWN_FAKE_IMAGE_NAME = "image_from_dropdown"


#      This type is the dict that comes from cachemachine:
#       https: //github.com/lsst-sqre/cachemachine/blob/4802ab7d78aec27b400f66b9af3324180910476e/src/cachemachine/types.py#L50-L69  # noqa: E501

CachemachineEntry = Dict[str, str]


@dataclass
class ImageInfo:
    """reference is a docker image reference.
    See:
     https://github.com/distribution/distribution/blob/main/reference/reference.go

    Example: "registry.hub.docker.com/lsstsqre/sciplat-lab:w_2021_13"
    """

    reference: str = field(init=False, default="")

    """display_name is a human-readable description of the image.

    Example: "Weekly 13"
    """
    display_name: str = field(init=False, default="")

    """digest is the hash of the last layer of the docker container.  If
    unknown, it will be the empty string.

    Example: "sha256:419c4b7e14603711b25fa9e0569460a753c4b2449fe275bb5f89743b01794a30"  # noqa: E501
    """
    digest: str = field(init=False, default="")

    """packed_string is the form in which the image info is packed into the
    JupyterHub options form and in which is is returned as the form
    selection.  It is specification, display_name, and digest
    concatenated with the pipe character.

    Example: "registry.hub.docker.com/lsstsqre/sciplat-lab:w_2021_13|Weekly 13|sha256:419c4b7e14603711b25fa9e0569460a753c4b2449fe275bb5f89743b01794a30"  # noqa: E501
    """
    packed_string: str = field(init=False, default="")

    def from_cachemachine_entry(self, entry: CachemachineEntry) -> None:
        """Take an entry from a cachemachine response, and set our fields
        from it.
        """
        self.reference = entry["image_url"]
        self.display_name = entry["name"]
        self.digest = entry["image_hash"] or ""  # Entry will have None not ""
        self.packed_string = self._pack()

    def from_packed_string(self, packed_string: str) -> None:
        """Take an entry from an ImageInfo packed_string, and set our fields
        from it.
        """
        fields = packed_string.split(FIELD_DELIMITER)
        assert len(fields) == 3, (
            "packed_string must have 3 "
            + f"{FIELD_DELIMITER}-separated fields"
        )
        self.reference = fields[0]
        self.display_name = fields[1]
        self.digest = fields[2]
        self.packed_string = self._pack()

    def _pack(self) -> str:
        return (
            self.reference
            + FIELD_DELIMITER
            + self.digest
            + FIELD_DELIMITER
            + self.display_name
        )


def dropdown_fake_image() -> ImageInfo:
    """This constructs an ImageInfo object that signals to that the
    dropdown field should be used to pick an image, rather than the cached
    image list.  This is used in options form templating and in determining
    which image was chosen (options.py and hooks.py, respectively)."""
    fake = ImageInfo()
    fake.from_packed_string(
        "{n}{d}{d}".format(n=DROPDOWN_FAKE_IMAGE_NAME, d=FIELD_DELIMITER)
    )
    return fake
