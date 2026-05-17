"""NEC version-aware rule dispatch.

`get_rules(edition)` returns the appropriate version module so the calc engine
can read constants and disallowed methods without hardcoding the version.
"""
from __future__ import annotations

from . import v2017, v2020, v2023


def get_rules(edition: str):
    """Return the NEC version module for the given edition string."""
    edition = (edition or "2023").strip()
    if edition == "2023":
        return v2023
    if edition == "2020":
        return v2020
    if edition == "2017":
        return v2017
    return v2023
