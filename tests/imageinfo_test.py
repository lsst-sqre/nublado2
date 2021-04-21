"""Tests for the ImageInfo class.
"""

from nublado2.imageinfo import FIELD_DELIMITER, ImageInfo

TEST_REF = "registry.hub.docker.com/lsstsqre/sciplat-lab:test_version"
TEST_DISPLAY_NAME = "Test Tag For Container"
TEST_DIGEST = "sha256:0123456789abcdef"  # Not a real sha256, obv.

TEST_PACKED_STRING = FIELD_DELIMITER.join(
    [TEST_REF, TEST_DISPLAY_NAME, TEST_DIGEST]
)
TEST_ENTRY = {
    "image_url": TEST_REF,
    "name": TEST_DISPLAY_NAME,
    "image_hash": TEST_DIGEST,
}


def test_creation_from_string() -> None:
    """Create from a string we assemble."""
    img = ImageInfo.from_packed_string(TEST_PACKED_STRING)
    assert img.reference == TEST_REF
    assert img.display_name == TEST_DISPLAY_NAME
    assert img.digest == TEST_DIGEST


def test_creation_from_cachemachine_entry() -> None:
    """Create from a dict like we'd get from cachemachine."""
    img = ImageInfo.from_cachemachine_entry(TEST_ENTRY)
    assert img.reference == TEST_REF
    assert img.display_name == TEST_DISPLAY_NAME
    assert img.digest == TEST_DIGEST


def test_creation_without_hash() -> None:
    """Create from a dict like we'd get from cachemachine but with no hash."""
    entry = dict(**TEST_ENTRY)
    del entry["image_hash"]
    img = ImageInfo.from_cachemachine_entry(entry)
    assert img.reference == TEST_REF
    assert img.display_name == TEST_DISPLAY_NAME
    assert img.digest == ""


def test_roundtrip() -> None:
    """Create an object from a cachemachine entry, get its packed string,
    create a new object from that, and test that the fields are the same."""
    img = ImageInfo.from_cachemachine_entry(TEST_ENTRY)
    newimg = ImageInfo.from_packed_string(img.packed_string)
    assert newimg.reference == TEST_REF
    assert newimg.display_name == TEST_DISPLAY_NAME
    assert newimg.digest == TEST_DIGEST
