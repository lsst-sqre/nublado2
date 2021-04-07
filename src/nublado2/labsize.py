from dataclasses import dataclass


@dataclass(frozen=True)
class LabSize:
    """The cpu and ram settings for a lab container."""

    cpu: float
    """Number of virtual CPUs to allocate for this lab.

    This can be a partial number, such as 2.5 or .5 vCPUs."""

    name: str
    """The name referring to this pairing of cpu and ram."""

    ram: str
    """Amount of memory to allocate for this lab.

    This is a string with special characters for units, such as
    2048M, or 2G."""
