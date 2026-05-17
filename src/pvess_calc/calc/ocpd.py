"""OCPD selection per NEC 240.6 / 690.9."""
from __future__ import annotations

from ..nec.tables import next_standard_ocpd


def select_ocpd(minimum_a: float) -> int:
    """Round up to the next standard rating (NEC 240.6)."""
    return next_standard_ocpd(minimum_a)
