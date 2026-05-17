"""Address parsing — input strings the wizard / CLI receives and split
them into the lookup keys our providers need.

The free-text address is whatever the user typed in `--address` (or
later, copied from a CRM). Goals:

  * Tolerant: accept "Phoenix, AZ", "Phoenix AZ", "Phoenix, AZ 85001",
    or a full street address.
  * Predictable: always returns a `ParsedAddress` (never raises) — fields
    are `None` when unparseable so downstream providers can decide to
    skip or fall back.
  * Lookup-key friendly: lowercase city/state for exact dict-key match
    against the JSON datasets.

This module deliberately does NOT geocode (no lat/lng). Phase K.3b adds
Mapbox / Google geocoding behind a provider interface.

Parsing strategy: prefer comma-delimited shapes (the universal US
address convention), fall back to whitespace splitting only when no
commas are present. Comma chunks make street / city / state-zip
boundaries unambiguous:

    "STREET, CITY, ST ZIP"   ← canonical
    "CITY, ST ZIP"
    "CITY, ST"
    "CITY ST"                ← whitespace fallback
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# Two-letter state abbreviations — used to anchor city/state extraction.
US_STATES: frozenset[str] = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
})


@dataclass(frozen=True)
class ParsedAddress:
    raw: str
    street: Optional[str] = None   # "2500 Hollow Hill Lane"
    city: Optional[str] = None     # "Lewisville" (Title Case)
    state: Optional[str] = None    # "TX" (uppercase)
    zip_code: Optional[str] = None # "75067"

    @property
    def city_state_key(self) -> Optional[str]:
        """Lookup key used by the JSON datasets: 'lewisville, tx'."""
        if self.city and self.state:
            return f"{self.city.lower()}, {self.state.lower()}"
        return None

    @property
    def state_key(self) -> Optional[str]:
        """For state-level providers (NEC adoption, IECC zone)."""
        return self.state.upper() if self.state else None


_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


def parse_address(raw: str) -> ParsedAddress:
    """Best-effort parser. Returns a ParsedAddress with whatever fields
    we could recover.

    Handles common shapes (most permissive first):
      "2500 Hollow Hill Lane, Lewisville, TX 75067"
      "Lewisville, TX 75067"
      "Lewisville, TX"
      "Lewisville TX"
      "TX"
      ""
    """
    if not raw or not raw.strip():
        return ParsedAddress(raw=raw)

    text = raw.strip()
    zip_code: Optional[str] = None
    m = _ZIP_RE.search(text)
    if m:
        zip_code = m.group(1)
        text = (text[: m.start()] + text[m.end() :]).strip(" ,")

    if "," in text:
        return _parse_comma_form(raw, text, zip_code)
    return _parse_whitespace_form(raw, text, zip_code)


def _parse_comma_form(raw: str, text: str, zip_code: Optional[str]) -> ParsedAddress:
    """Canonical 'STREET, CITY, ST' form (zip already stripped).

    The state lives in the LAST chunk (post-zip-strip). We grab it,
    treat the chunk before as city, and join any remaining earlier
    chunks as street.
    """
    chunks = [c.strip() for c in text.split(",") if c.strip()]
    if not chunks:
        return ParsedAddress(raw=raw, zip_code=zip_code)

    last = chunks[-1]
    # Last chunk is usually just "ST" — but for "Lewisville, TX 75067"
    # after zip-strip it's still "TX". For "TX 75067" with no comma we'd
    # not be here. Look for a valid state abbreviation as the last
    # whitespace-separated token of the last chunk.
    last_tokens = last.split()
    state: Optional[str] = None
    leftover_after_state: list[str] = []
    if last_tokens and last_tokens[-1].upper() in US_STATES:
        state = last_tokens[-1].upper()
        leftover_after_state = last_tokens[:-1]    # any text before the state
    elif last_tokens and last_tokens[0].upper() in US_STATES:
        state = last_tokens[0].upper()
        leftover_after_state = last_tokens[1:]

    if state is None:
        # Last chunk didn't contain a state — every chunk is just textual.
        # Best we can do: city = last chunk, street = earlier chunks.
        city = chunks[-1] or None
        street = ", ".join(chunks[:-1]) or None
        return ParsedAddress(
            raw=raw,
            street=street,
            city=_titlecase(city) if city else None,
            zip_code=zip_code,
        )

    # The state-bearing chunk has two possible shapes:
    #   1. "STATE" alone (canonical "STREET, CITY, ST" form) — no leftover.
    #      City = chunks[-2]; street = chunks[:-2].
    #   2. "CITY STATE" (user wrote "STREET, CITY ST ZIP" without the
    #      city/state comma) — leftover holds the city tokens.
    #      City = leftover; street = chunks[:-1] (everything else).
    #
    # The previous implementation merged both into one list and silently
    # picked the wrong element for shape #2, treating the street as the
    # city. That broke offline lookups for any full street address.
    if leftover_after_state:
        # Shape #2: city is inside the state chunk.
        city = " ".join(leftover_after_state)
        street_chunks = chunks[:-1]
    elif len(chunks) >= 2:
        # Shape #1: city is the previous chunk.
        city = chunks[-2]
        street_chunks = chunks[:-2]
    else:
        city = None
        street_chunks = []

    street = ", ".join(street_chunks) or None
    return ParsedAddress(
        raw=raw,
        street=street,
        city=_titlecase(city) if city else None,
        state=state,
        zip_code=zip_code,
    )


def _parse_whitespace_form(raw: str, text: str, zip_code: Optional[str]) -> ParsedAddress:
    """No commas — "Phoenix AZ" or just "AZ"."""
    tokens = text.split()
    state: Optional[str] = None
    state_idx: Optional[int] = None
    for i in range(len(tokens) - 1, -1, -1):
        if tokens[i].upper() in US_STATES:
            state = tokens[i].upper()
            state_idx = i
            break

    if state is None:
        # Whole string is treated as a city.
        return ParsedAddress(
            raw=raw,
            city=_titlecase(text) if text else None,
            zip_code=zip_code,
        )

    city_tokens = tokens[:state_idx]
    city = " ".join(city_tokens) or None
    return ParsedAddress(
        raw=raw,
        city=_titlecase(city) if city else None,
        state=state,
        zip_code=zip_code,
    )


def _titlecase(s: str) -> str:
    """Title-case city names. Lightweight — only used for display;
    lookup keys are lowercased independently."""
    return " ".join(w.capitalize() if w.islower() or w.isupper() else w
                    for w in s.split())
